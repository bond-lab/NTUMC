"""Blind Opus review of the senses flagged by the Haiku triage.

Two runs see the flagged senses under fresh random ids, shuffled
differently and without the Haiku reason; senses on which the runs
disagree (or are both UNSURE) go to adjudication with both reasons.

  build      write runN/batchNNN.tsv + runN/key.tsv for each language
  compare    write adjudicateNN.tsv + adjudicate-key.tsv from the two runs
  final      combine everything into final.tsv per language
"""

import argparse
import csv
import glob
import random
from collections import Counter
from pathlib import Path

LANGS = ("cmn", "id", "zsm")
NOTE_TAGS = {"FORM", "MS", "ID"}
COLS = ["word", "other_words_in_synset", "english_words", "english_definition",
        "own_definition"]


def read_tsv(path: Path) -> list[dict]:
    """Rows of a tab-separated file with a header."""
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE))


def write_tsv(path: Path, header: list[str], rows: list[list]) -> None:
    """Write a tab-separated file with a header."""
    with open(path, "w", encoding="utf-8", newline="") as fh:
        t = csv.writer(fh, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE,
                       escapechar="\\")
        t.writerow(header)
        t.writerows(rows)


def flagged(triage: Path, lang: str) -> list[dict]:
    """Triage rows flagged SUSPECT, with the Haiku reason added."""
    reason = {}
    for f in sorted(glob.glob(f"{triage}/{lang}/batch*-suspects.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id"):
                reason[r["id"]] = (r.get("reason") or "").strip()
    rows = []
    for f in sorted(glob.glob(f"{triage}/{lang}/batch[0-9][0-9][0-9].tsv")):
        for r in read_tsv(Path(f)):
            if r["id"] in reason:
                r["haiku"] = reason[r["id"]]
                rows.append(r)
    return rows


def build(triage: Path, out: Path, size: int, seed: int) -> None:
    """Write two blind, differently shuffled batch sets per language."""
    for lang in LANGS:
        rows = flagged(triage, lang)
        for run in (1, 2):
            d = out / lang / f"run{run}"
            d.mkdir(parents=True, exist_ok=True)
            rng = random.Random(seed * 10 + run + LANGS.index(lang) * 100)
            ids = rng.sample(range(100000, 999999), len(rows))
            order = list(zip(ids, rows))
            rng.shuffle(order)
            write_tsv(d / "key.tsv", ["id", "triage_id", "synset", "word"],
                      [[i, r["id"], r["synset"], r["word"]] for i, r in order])
            for b in range(0, len(order), size):
                write_tsv(d / f"batch{b // size + 1:03d}.tsv", ["id"] + COLS,
                          [[i] + [r[c] for c in COLS] for i, r in order[b:b + size]])
        print(lang, len(rows), "flagged ->", -(-len(rows) // size), "batches per run")


def verdicts(d: Path) -> dict:
    """triage_id -> (verdict, reason) for one run."""
    key = {r["id"]: r["triage_id"] for r in read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-review.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = ((r.get("verdict") or "").strip().upper(),
                                     (r.get("reason") or "").strip())
    return out


def notes(d: Path) -> dict:
    """triage_id -> set of form tags (FORM, MS, ID) given in one run."""
    key = {r["id"]: r["triage_id"] for r in read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9][0-9]-review.tsv")):
        for r in read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = set((r.get("note") or "").upper().split()) & NOTE_TAGS
    return out


def compare(triage: Path, out: Path, size: int, seed: int) -> None:
    """Write adjudication batches for disagreements and double UNSURE."""
    for lang in LANGS:
        rows = {r["id"]: r for r in flagged(triage, lang)}
        r1, r2 = verdicts(out / lang / "run1"), verdicts(out / lang / "run2")
        pairs = Counter((r1.get(k, ("MISSING",))[0], r2.get(k, ("MISSING",))[0]) for k in rows)
        print(f"== {lang}: run1 rows x run2 cols")
        for a in ("OK", "WRONG", "UNSURE", "MISSING"):
            print(f"  {a:7}", {b: pairs[(a, b)] for b in ("OK", "WRONG", "UNSURE", "MISSING")})
        todo = [k for k in rows
                if r1.get(k, ("MISSING",))[0] != r2.get(k, ("MISSING",))[0]
                or r1.get(k, ("MISSING",))[0] not in ("OK", "WRONG")]
        rng = random.Random(seed + 7 + LANGS.index(lang))
        rng.shuffle(todo)
        ids = rng.sample(range(100000, 999999), len(todo))
        d = out / lang / "adjudicate"
        d.mkdir(parents=True, exist_ok=True)
        write_tsv(d / "key.tsv", ["id", "triage_id"], [[i, k] for i, k in zip(ids, todo)])
        for b in range(0, len(todo), size):
            write_tsv(d / f"batch{b // size + 1:03d}.tsv",
                      ["id"] + COLS + ["review_a", "reason_a", "review_b", "reason_b"],
                      [[i] + [rows[k][c] for c in COLS]
                       + list(r1.get(k, ("MISSING", ""))) + list(r2.get(k, ("MISSING", "")))
                       for i, k in zip(ids[b:b + size], todo[b:b + size])])
        print(f"  to adjudicate: {len(todo)} -> {-(-len(todo) // size)} batches")


def final(triage: Path, out: Path) -> None:
    """Combine triage, both runs and adjudication into final.tsv."""
    for lang in LANGS:
        rows = flagged(triage, lang)
        r1, r2 = verdicts(out / lang / "run1"), verdicts(out / lang / "run2")
        adj = verdicts(out / lang / "adjudicate") if (out / lang / "adjudicate").exists() else {}
        n1, n2 = notes(out / lang / "run1"), notes(out / lang / "run2")
        res, tab = [], Counter()
        for r in rows:
            k = r["id"]
            v1, v2 = r1.get(k, ("MISSING", "")), r2.get(k, ("MISSING", ""))
            if v1[0] == v2[0] and v1[0] in ("OK", "WRONG"):
                fin, by, why = v1[0], "both", v1[1] or v2[1]
            elif k in adj:
                fin, by, why = adj[k][0], "adjudication", adj[k][1]
            else:
                fin, by, why = "UNSURE", "none", ""
            act = {"WRONG": "remove", "OK": "keep"}.get(fin, "lower")
            tab[act] += 1
            a, b = n1.get(k, set()), n2.get(k, set())
            res.append([r["synset"], r["word"], r["haiku"], v1[0], v2[0], fin, act, by, why,
                        " ".join(sorted(a & b)), " ".join(sorted(a ^ b))])
        write_tsv(out / lang / "final.tsv",
                  ["synset", "word", "haiku_reason", "run1", "run2", "final", "action",
                   "decided_by", "reason", "note_both", "note_one"], res)
        print(lang, dict(tab))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("build", "compare", "final"))
    ap.add_argument("--triage", type=Path, default=Path("build/triage"))
    ap.add_argument("--out", type=Path, default=Path("build/triage-opus"))
    ap.add_argument("--size", type=int, default=150)
    ap.add_argument("--seed", type=int, default=20261024)
    a = ap.parse_args()
    if a.step == "build":
        build(a.triage, a.out, a.size, a.seed)
    elif a.step == "compare":
        compare(a.triage, a.out, 100, a.seed)
    else:
        final(a.triage, a.out)


if __name__ == "__main__":
    main()
