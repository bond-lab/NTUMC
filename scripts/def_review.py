"""Blind double review of the Indonesian definitions of Wordnet Bahasa.

Each definition is judged OK, PARTIAL, WRONG or UNSURE against the English
synset by two runs that see it under fresh random ids in different
shuffles; definitions the runs disagree on (or are both UNSURE about) go to
an adjudicator with both verdicts, reasons and suggested fixes.

  build    write OUT/runN/batchNNN.tsv + OUT/runN/key.tsv
  compare  write OUT/adjudicate/batchNNN.tsv + key.tsv from the two runs
  final    combine everything into OUT/final.tsv

  def_review.py build WNB_ID_XML --en-data WN_DIR
"""

import argparse
import glob
import random
from collections import Counter
from pathlib import Path

import triage_review as tr

COLS = ["indonesian_words", "english_words", "english_definition", "own_definition"]
VERDICTS = ("OK", "PARTIAL", "WRONG")


def definitions(xml: Path, en_data: Path) -> list[dict]:
    """One row per synset of xml with an Indonesian definition."""
    import wn
    from wn import lmf

    wn.config.data_directory = str(en_data)
    en = wn.Wordnet("omw-en:2.0")
    lex = lmf.load(str(xml), progress_handler=None)["lexicons"][0]
    words: dict[str, list[str]] = {}
    for e in lex["entries"]:
        for s in e.get("senses", []):
            words.setdefault(s["synset"], []).append(e["lemma"]["writtenForm"])
    rows = []
    for ss in lex["synsets"]:
        d = [x for x in ss.get("definitions", []) if not x.get("language")]
        if not d:
            continue
        ew = ed = ""
        if ss.get("ili") and ss["ili"] != "in" and (e := en.synsets(ili=ss["ili"])):
            ew, ed = ", ".join(e[0].lemmas()), e[0].definition() or ""
        rows.append({"synset": ss["id"], "indonesian_words": ", ".join(words.get(ss["id"], [])),
                     "english_words": ew, "english_definition": ed,
                     "own_definition": d[0]["text"]})
    return rows


def build(a: argparse.Namespace) -> None:
    """Write two blind, differently shuffled batch sets and the source table."""
    rows = definitions(a.xml, a.en_data)
    a.out.mkdir(parents=True, exist_ok=True)
    tr.write_tsv(a.out / "definitions.tsv", ["synset", *COLS],
                 [[r["synset"], *(r[c] for c in COLS)] for r in rows])
    for run in (1, 2):
        d = a.out / f"run{run}"
        d.mkdir(parents=True, exist_ok=True)
        rng = random.Random(a.seed * 10 + run)
        ids = rng.sample(range(100000, 999999), len(rows))
        order = list(zip(ids, rows))
        rng.shuffle(order)
        tr.write_tsv(d / "key.tsv", ["id", "synset"], [[i, r["synset"]] for i, r in order])
        for b in range(0, len(order), a.size):
            tr.write_tsv(d / f"batch{b // a.size + 1:03d}.tsv", ["id", *COLS],
                         [[i, *(r[c] for c in COLS)] for i, r in order[b:b + a.size]])
    print(len(rows), "definitions ->", -(-len(rows) // a.size), "batches per run")


def verdicts(d: Path) -> dict[str, tuple[str, str, str]]:
    """synset -> (verdict, reason, suggestion) for one run."""
    key = {r["id"]: r["synset"] for r in tr.read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-review.tsv")):
        for r in tr.read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = ((r.get("verdict") or "").strip().upper(),
                                     (r.get("reason") or "").strip(),
                                     (r.get("suggestion") or "").strip())
    return out


def settled(v1: tuple, v2: tuple) -> bool:
    """True if the two runs agree on OK, PARTIAL or WRONG."""
    return v1[0] == v2[0] and v1[0] in VERDICTS


def compare(a: argparse.Namespace) -> None:
    """Write adjudication batches for disagreements and double UNSURE."""
    rows = {r["synset"]: r for r in tr.read_tsv(a.out / "definitions.tsv")}
    r1, r2 = verdicts(a.out / "run1"), verdicts(a.out / "run2")
    miss = ("MISSING", "", "")
    pairs = Counter((r1.get(k, miss)[0], r2.get(k, miss)[0]) for k in rows)
    print("run1 rows x run2 cols")
    for v in (*VERDICTS, "UNSURE", "MISSING"):
        print(f"  {v:7}", {w: pairs[(v, w)] for w in (*VERDICTS, "UNSURE", "MISSING")})
    todo = [k for k in rows if not settled(r1.get(k, miss), r2.get(k, miss))]
    rng = random.Random(a.seed + 7)
    rng.shuffle(todo)
    ids = rng.sample(range(100000, 999999), len(todo))
    d = a.out / "adjudicate"
    d.mkdir(parents=True, exist_ok=True)
    tr.write_tsv(d / "key.tsv", ["id", "synset"], [[i, k] for i, k in zip(ids, todo)])
    size = 100
    for b in range(0, len(todo), size):
        tr.write_tsv(d / f"batch{b // size + 1:03d}.tsv",
                     ["id", *COLS, "review_a", "reason_a", "suggestion_a",
                      "review_b", "reason_b", "suggestion_b"],
                     [[i, *(rows[k][c] for c in COLS), *r1.get(k, miss), *r2.get(k, miss)]
                      for i, k in zip(ids[b:b + size], todo[b:b + size])])
    print(f"to adjudicate: {len(todo)} -> {-(-len(todo) // size)} batches")


def final(a: argparse.Namespace) -> None:
    """Combine both runs and the adjudication into OUT/final.tsv."""
    rows = tr.read_tsv(a.out / "definitions.tsv")
    r1, r2 = verdicts(a.out / "run1"), verdicts(a.out / "run2")
    adj = verdicts(a.out / "adjudicate") if (a.out / "adjudicate").exists() else {}
    miss = ("MISSING", "", "")
    res, tab = [], Counter()
    for r in rows:
        k = r["synset"]
        v1, v2 = r1.get(k, miss), r2.get(k, miss)
        if settled(v1, v2):
            fin, by, why = v1[0], "both", v1[1] or v2[1]
            sugg = v1[2] or v2[2]
        elif k in adj:
            fin, by, why, sugg = adj[k][0], "adjudication", adj[k][1], adj[k][2]
        else:
            fin, by, why, sugg = "UNSURE", "none", "", ""
        tab[fin] += 1
        res.append([k, r["own_definition"], fin, by, why, sugg, v1[0], v2[0], v1[2], v2[2]])
    tr.write_tsv(a.out / "final.tsv",
                 ["synset", "definition", "final", "decided_by", "reason", "suggestion",
                  "run1", "run2", "suggestion1", "suggestion2"], res)
    print(dict(tab))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("build", "compare", "final"))
    ap.add_argument("xml", type=Path, nargs="?", help="wnb-id XML")
    ap.add_argument("--en-data", type=Path, default=Path.home() / ".wn_data",
                    help="wn data directory with omw-en:2.0")
    ap.add_argument("--out", type=Path, default=Path("build/def-review/id"))
    ap.add_argument("--size", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261025)
    a = ap.parse_args()
    {"build": build, "compare": compare, "final": final}[a.step](a)


if __name__ == "__main__":
    main()
