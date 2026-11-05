"""Pilot of the calibrated sense review on wnja senses no audit flagged.

Two blind runs of the `info` prompt (scripts/prompt_calibration.py; Claude
Sonnet) over a random sample of the never-flagged senses, each under fresh
ids and a fresh shuffle.  The spot-check items are left out (they are
development data).

  make   write OUT/runN/batchNN.tsv, key.tsv and PROMPT.md, and OUT/items.tsv
  final  combine the runs: remove if both say WRONG, keep if both say OK,
         otherwise lower to 0.5 and queue for a person; write OUT/final.tsv

  uv run --with jamdict --with jamdict-data python scripts/pilot_review.py make
"""

import argparse
import glob
import random
from collections import Counter
from pathlib import Path

import prompt_calibration as pc
import spot_check as sc
import triage_review as tr

SEED = 20261107
COLS = pc.COLS["info"]


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


def decide(v1: str, v2: str) -> str:
    """remove, keep or lower (for a person) from two runs' verdicts."""
    if v1 == v2 == "WRONG":
        return "remove"
    if v1 == v2 == "OK":
        return "keep"
    return "lower"


def final(a: argparse.Namespace) -> None:
    """Combine the two runs into OUT/final.tsv."""
    items = tr.read_tsv(a.out / "items.tsv")
    r1, r2 = verdicts(a.out / "run1"), verdicts(a.out / "run2")
    miss = ("MISSING", "")
    rows, tab = [], Counter()
    for it in items:
        k = (it["synset"], it["word"])
        v1, v2 = r1.get(k, miss), r2.get(k, miss)
        act = decide(v1[0], v2[0])
        tab[act] += 1
        rows.append([it["synset"], it["word"], it["english_words"], act, v1[0], v2[0],
                     v1[1], v2[1]])
    tr.write_tsv(a.out / "final.tsv", ["synset", "word", "english_words", "action", "run1",
                                       "run2", "reason1", "reason2"], rows)
    print(dict(tab), "missing:", sum(1 for k in map(lambda x: (x["synset"], x["word"]), items)
                                     if k not in r1 or k not in r2))


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("make", "final"))
    ap.add_argument("--wnja", type=Path, default=Path("../wnja"), help="wnja checkout, built")
    ap.add_argument("--spot", type=Path, default=Path("docs/quality-sample/spot-check"))
    ap.add_argument("--issue8", type=Path,
                    default=Path("docs/quality-sample/wnja-opus2/final.tsv"))
    ap.add_argument("--out", type=Path, default=Path("build/pilot-review"))
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--size", type=int, default=200)
    a = ap.parse_args()
    make(a) if a.step == "make" else final(a)


if __name__ == "__main__":
    main()
