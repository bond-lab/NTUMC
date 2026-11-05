"""Pilot of the calibrated sense review on wnja senses no audit flagged.

Two blind runs of the `info` prompt (scripts/prompt_calibration.py; Claude
Sonnet) over a random sample of the never-flagged senses, each under fresh
ids and a fresh shuffle.  The spot-check items are left out (they are
development data).

  make   write OUT/runN/batchNN.tsv, key.tsv and PROMPT.md, and OUT/items.tsv
  final  combine the runs (see `decide`) into OUT/final.tsv
  sheet  write a blind sheet of a stratified sample of the decisions for a
         native checker to SHEET/, with the key in SHEET/key/
  check  score a returned sheet (SHEET/returned/) against the decisions
  blind  write the senses with one action, under fresh ids, to OUT/blind-ACTION/
         (for a reviewer from another company)

  uv run --with jamdict --with jamdict-data python scripts/pilot_review.py make
"""

import argparse
import glob
import random
from collections import Counter, defaultdict
from pathlib import Path

import prompt_calibration as pc
import spot_check as sc
import triage_review as tr

SEED = 20261107
COLS = pc.COLS["info"]
SAMPLE = {"remove": 50, "queue": 30, "lower": 30, "keep": 30}
SHEET = ["item", "word", "other_words_in_synset", "english_words", "english_definition",
         "own_definition", "meaning", "form", "comment"]


def make(a: argparse.Namespace) -> None:
    """Sample never-flagged senses and write two blind batch sets."""
    pop = sc.population_ja(a)["unflagged"]
    spot = {(k["synset"], k["word"]) for k in tr.read_tsv(a.spot / "key" / "ja-key.tsv")}
    pop = sorted((x for x in pop if (x["synset"], x["word"]) not in spot),
                 key=lambda x: (x["synset"], x["word"]))
    sample = random.Random(SEED).sample(pop, a.n)
    ctx = pc.context(a.wnja)
    rows = []
    for x in sample:
        c = x["ctx"]
        others = " ".join(w for w in c["other_words_in_synset"].split() if w != x["word"])
        rows.append([x["synset"], x["word"], others, c["english_words"], c["english_definition"],
                     c["own_definition"], *pc.extra(ctx, sc.bare(x["synset"]), x["word"])])
    a.out.mkdir(parents=True, exist_ok=True)
    tr.write_tsv(a.out / "items.tsv", ["synset", *COLS], rows)
    for run in (1, 2):
        d = a.out / f"run{run}"
        d.mkdir(exist_ok=True)
        rng = random.Random(SEED + run)
        order = rows[:]
        rng.shuffle(order)
        ids = rng.sample(range(100000, 999999), len(order))
        tr.write_tsv(d / "key.tsv", ["id", "synset", "word"],
                     [[i, r[0], r[1]] for i, r in zip(ids, order)])
        for b in range(0, len(order), a.size):
            tr.write_tsv(d / f"batch{b // a.size + 1:02d}.tsv", ["id", *COLS],
                         [[i, *r[1:]] for i, r in zip(ids[b:b + a.size], order[b:b + a.size])])
        (d / "PROMPT.md").write_text(pc.PROMPTS["info"] + "\n\n" + pc.OUTPUT + "\n",
                                     encoding="utf-8")
    print(f"{len(rows)} of {len(pop)} never-flagged senses, {-(-len(rows) // a.size)} batches per run")


def verdicts(d: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(synset, word) -> (verdict, reason) for one run."""
    key = {r["id"]: (r["synset"], r["word"]) for r in tr.read_tsv(d / "key.tsv")}
    out = {}
    for f in sorted(glob.glob(f"{d}/batch[0-9][0-9]-review.tsv")):
        for r in tr.read_tsv(Path(f)):
            if r.get("id") in key:
                out[key[r["id"]]] = ((r.get("verdict") or "").strip().upper(),
                                     (r.get("reason") or "").strip())
    return out


def decide(v1: str, v2: str, in_jmdict: bool) -> str:
    """The action for a sense from two runs' verdicts.

    keep    both OK
    remove  both WRONG
    lower   to 0.8, no person: one OK and one UNSURE, or both UNSURE and the
            word is in JMdict
    queue   lower to 0.5 and queue for a person: everything else (OK and
            WRONG, WRONG and UNSURE, both UNSURE and not in JMdict, missing)
    """
    pair = {v1, v2}
    if pair == {"OK"}:
        return "keep"
    if pair == {"WRONG"}:
        return "remove"
    if pair == {"OK", "UNSURE"} or (pair == {"UNSURE"} and in_jmdict):
        return "lower"
    return "queue"


def final(a: argparse.Namespace) -> None:
    """Combine the two runs into OUT/final.tsv."""
    items = tr.read_tsv(a.out / "items.tsv")
    r1, r2 = verdicts(a.out / "run1"), verdicts(a.out / "run2")
    miss = ("MISSING", "")
    rows, tab = [], Counter()
    for it in items:
        k = (it["synset"], it["word"])
        v1, v2 = r1.get(k, miss), r2.get(k, miss)
        act = decide(v1[0], v2[0], bool(it["jmdict"]))
        tab[act] += 1
        rows.append([it["synset"], it["word"], it["english_words"], act, v1[0], v2[0],
                     v1[1], v2[1]])
    tr.write_tsv(a.out / "final.tsv", ["synset", "word", "english_words", "action", "run1",
                                       "run2", "reason1", "reason2"], rows)
    keys = [(x["synset"], x["word"]) for x in items]
    print(dict(tab), "missing:", sum(1 for k in keys if k not in r1 or k not in r2))


def sheet(a: argparse.Namespace) -> None:
    """Write a blind sheet of a stratified sample of the decisions, and its key."""
    items = {(r["synset"], r["word"]): r for r in tr.read_tsv(a.out / "items.tsv")}
    final = tr.read_tsv(a.out / "final.tsv")
    rng = random.Random(f"{SEED}-sheet")
    picked = []
    for act, n in SAMPLE.items():
        pool = [r for r in final if r["action"] == act]
        picked += [(act, r) for r in rng.sample(pool, min(n, len(pool)))]
    rng.shuffle(picked)
    rows, key = [], []
    for n, (act, r) in enumerate(picked, 1):
        it = items[(r["synset"], r["word"])]
        rows.append([f"pc-{n:03d}", r["word"], it["other_words_in_synset"], it["english_words"],
                     it["english_definition"], it["own_definition"], "", "", ""])
        key.append([f"pc-{n:03d}", act, r["synset"], r["word"], r["run1"], r["run2"],
                    r["reason1"], r["reason2"]])
    (a.sheet / "key").mkdir(parents=True, exist_ok=True)
    tr.write_tsv(a.sheet / "ja-pilot-sheet.tsv", SHEET, rows)
    tr.write_tsv(a.sheet / "key" / "ja-pilot-key.tsv",
                 ["item", "action", "synset", "word", "run1", "run2", "reason1", "reason2"], key)
    print(f"{len(rows)} items: {dict(Counter(act for act, _ in picked))}")


def check(a: argparse.Namespace) -> None:
    """Per action: the checker's answers and the share of definite answers WRONG."""
    key = {k["item"]: k["action"] for k in tr.read_tsv(a.sheet / "key" / "ja-pilot-key.tsv")}
    got = {r["item"]: (r.get("meaning") or "").strip().upper()
           for r in tr.read_tsv(sc.filled(a.sheet, "ja-pilot-sheet.tsv"))}
    tab = defaultdict(Counter)
    for item, act in key.items():
        tab[act][got.get(item) or "BLANK"] += 1
    rows = []
    for act in SAMPLE:
        c = tab[act]
        n = c["OK"] + c["WRONG"]
        lo, hi = sc.wilson(c["WRONG"], n) if n else (0.0, 0.0)
        rows.append([act, c["OK"], c["WRONG"], c["UNSURE"], c["BLANK"],
                     f"{c['WRONG'] / n:.2f}" if n else "", f"{lo:.2f}-{hi:.2f}" if n else ""])
    head = ["action", "ok", "wrong", "unsure", "blank", "wrong_share", "wrong_95ci"]
    tr.write_tsv(a.sheet / "key" / "score.tsv", head, rows)
    print("\t".join(head))
    for r in rows:
        print("\t".join(map(str, r)))


def blind(a: argparse.Namespace) -> None:
    """Write the senses with one action under fresh ids, for another reviewer."""
    acts = {(r["synset"], r["word"]) for r in tr.read_tsv(a.out / "final.tsv")
            if r["action"] == a.action}
    rows = [r for r in tr.read_tsv(a.out / "items.tsv") if (r["synset"], r["word"]) in acts]
    rng = random.Random(f"{SEED}-{a.action}")
    rng.shuffle(rows)
    ids = rng.sample(range(100000, 999999), len(rows))
    d = a.out / f"blind-{a.action}"
    d.mkdir(parents=True, exist_ok=True)
    tr.write_tsv(d / "key.tsv", ["id", "synset", "word"],
                 [[i, r["synset"], r["word"]] for i, r in zip(ids, rows)])
    for b in range(0, len(rows), a.size):
        tr.write_tsv(d / f"batch{b // a.size + 1:02d}.tsv", ["id", *COLS],
                     [[i, *(r[c] for c in COLS)] for i, r in zip(ids[b:b + a.size],
                                                                 rows[b:b + a.size])])
    (d / "PROMPT.md").write_text(pc.PROMPTS["info"] + "\n\n" + pc.OUTPUT + "\n", encoding="utf-8")
    print(f"{len(rows)} senses in {-(-len(rows) // a.size)} batches in {d}")


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("make", "final", "sheet", "check", "blind"))
    ap.add_argument("--wnja", type=Path, default=Path("../wnja"), help="wnja checkout, built")
    ap.add_argument("--spot", type=Path, default=Path("docs/quality-sample/spot-check"))
    ap.add_argument("--issue8", type=Path,
                    default=Path("docs/quality-sample/wnja-opus2/final.tsv"))
    ap.add_argument("--out", type=Path, default=Path("build/pilot-review"))
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--size", type=int, default=200)
    ap.add_argument("--sheet", type=Path, default=Path("docs/quality-sample/pilot-check"))
    ap.add_argument("--action", default="remove", help="for blind: the senses to write")
    a = ap.parse_args()
    {"make": make, "final": final, "sheet": sheet, "check": check, "blind": blind}[a.step](a)


if __name__ == "__main__":
    main()
