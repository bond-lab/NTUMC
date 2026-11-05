"""Native-speaker recheck of the JSemCor senses the LLM review rejected.

JSemCor translators used a Japanese word for an English word tagged with a
synset; wnja added the pairs a blind double Opus review accepted (issue
#11).  The spot check found the rejections mostly wrong (17 of 20 judged
OK), so the rest go to a native checker, blind, with the sentence pair.

  make   write OUT/ja-jsemcor-sheet.tsv (all rejected pairs not already in the
         spot check, in random order, with the corpus example), an overlap
         sheet of 50 for a second checker and OUT/key/ja-jsemcor-key.tsv

  jsemcor_recheck.py make [--wnja ../wnja] [--out docs/quality-sample/jsemcor-recheck]
"""

import argparse
import random
from pathlib import Path

import spot_check as sc
import triage_review as tr

SEED = 20261105
SHEET = ["item", "word", "other_words_in_synset", "english_words", "english_definition",
         "own_definition", "example_en", "example_ja", "meaning", "form", "comment"]
KEY = ["item", "synset", "word", "run1", "run2", "final", "decided_by", "model_reason"]


def rejected(wnja: Path, checked: set[tuple[str, str]]) -> list[dict]:
    """The pairs the review rejected (WRONG or MWE), not added and not yet checked."""
    corr = tr.read_tsv(wnja / "corrections" / "senses.tsv")
    added = {(sc.bare(r["synset_id"]), r["lemma"]) for r in corr if r["action"] == "add"}
    return [r for r in tr.read_tsv(wnja / "audit" / "reviews" / "jsemcor" / "verdicts.tsv")
            if r["final"] in ("WRONG", "MWE") and (r["synset"], r["lemma"]) not in added
            and (r["synset"], r["lemma"]) not in checked]


def examples(wnja: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """(synset, lemma) -> (English, Japanese) example sentence from the suggestions."""
    out = {}
    for r in tr.read_tsv(wnja / "corrections" / "review" / "jsemcor-suggestions.tsv"):
        out.setdefault((r["synset"], r["lemma"]), (r["example_en"], r["example_ja"]))
    return out


def make(a: argparse.Namespace) -> None:
    """Write the blind sheet, the overlap sheet and the key."""
    spot = tr.read_tsv(a.spot / "key" / "ja-key.tsv")
    checked = {(sc.bare(k["synset"]), k["word"]) for k in spot if k["stratum"] == "jsemcor-reject"}
    rows = rejected(a.wnja, checked)
    ctx, _ = sc.ja_context(a)
    ex = examples(a.wnja)
    rng = random.Random(SEED)
    rng.shuffle(rows)
    sheet, key, missing = [], [], 0
    for r in rows:
        c = ctx.get(r["synset"])
        if c is None:
            missing += 1
            continue
        item = f"jc-{len(sheet) + 1:04d}"
        others = " ".join(w for w in c["other_words_in_synset"].split() if w != r["lemma"])
        en, ja = ex.get((r["synset"], r["lemma"]), ("", ""))
        sheet.append([item, r["lemma"], others, c["english_words"], c["english_definition"],
                      c["own_definition"], en, ja, "", "", ""])
        key.append([item, "wnja-" + r["synset"], r["lemma"], r["run1"], r["run2"], r["final"],
                    r["decided_by"], r["reason"]])
    (a.out / "key").mkdir(parents=True, exist_ok=True)
    tr.write_tsv(a.out / "ja-jsemcor-sheet.tsv", SHEET, sheet)
    overlap = random.Random(f"{SEED}-overlap").sample(sheet, min(a.overlap, len(sheet)))
    tr.write_tsv(a.out / "ja-jsemcor-overlap-sheet.tsv", SHEET, overlap)
    tr.write_tsv(a.out / "key" / "ja-jsemcor-key.tsv", KEY, key)
    print(f"{len(sheet)} items ({len(checked)} already in the spot check, "
          f"{missing} with no synset in wnja left out); {len(overlap)} in the overlap sheet")


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=("make",))
    ap.add_argument("--wnja", type=Path, default=Path("../wnja"), help="wnja checkout, built")
    ap.add_argument("--spot", type=Path, default=Path("docs/quality-sample/spot-check"))
    ap.add_argument("--out", type=Path, default=Path("docs/quality-sample/jsemcor-recheck"))
    ap.add_argument("--overlap", type=int, default=50, help="items for a second checker")
    make(ap.parse_args())


if __name__ == "__main__":
    main()
