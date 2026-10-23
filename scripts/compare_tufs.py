#!/usr/bin/env python3
"""Compare released wordnets with the TUFS Basic Vocabulary wordnets.

TUFS (tufs-ja, tufs-zh, tufs-id, tufs-ms) is small and hand-built, so it
works as a check on the basic vocabulary of wnja, COW and Wordnet
Bahasa.  Synsets are matched by ILI, or by PWN offset-pos where a synset
has no ILI.  All written forms (lemma and variant forms) are compared
after NFKC normalisation, ignoring spaces and NTU-MC's '+的' suffix.

For each language this reports synset coverage, sense agreement, TUFS
words found only in other synsets (likely errors on one side), and
shared synsets with no lemma in common; the disagreements are written to
a TSV for review.

Both wordnets must already be added to the wn data directory.

Usage:
    scripts/compare_tufs.py [--data-dir DIR] [-o docs/tufs-comparison]
"""

import argparse
import csv
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import wn

# (language, ours, tufs)
PAIRS = [
    ("ja", "wnja:2.0", "tufs-ja:2026.04.06"),
    ("cmn", "cow:1.0", "tufs-zh:2026.04.06"),
    ("id", "wnb-id:1.3", "tufs-id:2026.04.06"),
    ("zsm", "wnb-zsm:1.3", "tufs-ms:2026.04.06"),
]
OFFSET = re.compile(r"(\d{8}-[a-z])$")


def norm(lemma: str) -> str:
    """Normalise a lemma for comparison."""
    lemma = unicodedata.normalize("NFKC", lemma).replace("+的", "")
    return lemma.replace(" ", "").replace("_", "").casefold()


def key(synset: wn.Synset) -> str | None:
    """Comparison key: the ILI, else the PWN offset-pos from the ID."""
    if synset.ili:
        return synset.ili
    m = OFFSET.search(synset.id)
    return m.group(1) if m else None


def index(spec: str) -> tuple[dict[str, set[str]], dict[str, set[str]], dict]:
    """Map key -> normalised lemmas, lemma -> keys, and key -> example synset."""
    by_key: dict[str, set[str]] = defaultdict(set)
    by_lemma: dict[str, set[str]] = defaultdict(set)
    synsets = {}
    for ss in wn.Wordnet(spec).synsets():
        k = key(ss)
        if k is None:
            continue
        synsets[k] = ss
        # all written forms (wnja keeps kana spellings as extra forms)
        for word in ss.words():
            for form in word.forms():
                n = norm(form)
                by_key[k].add(n)
                by_lemma[n].add(k)
    return by_key, by_lemma, synsets


def compare(lang: str, ours: str, tufs: str, out: csv.writer) -> dict:
    """Compare one pair; write disagreements; return summary figures."""
    o_key, o_lemma, o_ss = index(ours)
    t_key, _, t_ss = index(tufs)
    t_keys = [k for k in t_key if t_key[k]]
    shared = [k for k in t_keys if o_key.get(k)]
    pairs = [(k, w) for k in t_keys for w in t_key[k]]
    agree = [(k, w) for k, w in pairs if w in o_key.get(k, set())]
    elsewhere = [(k, w) for k, w in pairs
                 if w not in o_key.get(k, set()) and o_lemma.get(w)]
    absent = [(k, w) for k, w in pairs if not o_lemma.get(w)]
    disjoint = [k for k in shared if not (t_key[k] & o_key[k])]

    def gloss(k: str) -> str:
        ss = t_ss.get(k) or o_ss.get(k)
        en = ss.translate(lexicon="omw-en:2.0") if ss else []
        return (en[0].definition() or "")[:70] if en else ""

    for k, w in elsewhere:
        out.writerow([lang, "word_in_other_synset", k, w,
                      " ".join(sorted(o_key.get(k, set()))),
                      " ".join(sorted(o_lemma[w])[:5]), gloss(k)])
    for k in disjoint:
        out.writerow([lang, "no_shared_lemma", k, " ".join(sorted(t_key[k])),
                      " ".join(sorted(o_key[k])), "", gloss(k)])
    for k in t_keys:
        if not o_key.get(k):
            out.writerow([lang, "synset_missing", k, " ".join(sorted(t_key[k])),
                          "", "", gloss(k)])
    return {
        "lang": lang, "ours": ours, "tufs": tufs,
        "tufs_synsets": len(t_keys), "shared_synsets": len(shared),
        "tufs_senses": len(pairs), "agree": len(agree),
        "elsewhere": len(elsewhere), "absent": len(absent),
        "disjoint": len(disjoint),
    }


def pct(n: int, d: int) -> str:
    """Format n/d as a percentage."""
    return f"{100 * n / d:.1f}%" if d else "–"


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", help="wn data directory")
    parser.add_argument("-o", "--out", default="docs/tufs-comparison",
                        help="Output prefix (writes PREFIX.md and PREFIX.tsv)")
    args = parser.parse_args()
    if args.data_dir:
        wn.config.data_directory = args.data_dir

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    with open(out.with_suffix(".tsv"), "w", encoding="utf-8", newline="") as fh:
        tsv = csv.writer(fh, delimiter="\t", lineterminator="\n")
        tsv.writerow(["lang", "kind", "synset", "tufs", "ours_in_synset",
                      "ours_synsets_for_word", "english_definition"])
        for lang, ours, tufs in PAIRS:
            rows.append(compare(lang, ours, tufs, tsv))

    lines = ["| | " + " | ".join(f"{r['ours']} vs {r['tufs'].split(':')[0]}"
                                  for r in rows) + " |",
             "|---|" + "---|" * len(rows)]
    def line(label, f):
        lines.append(f"| {label} | " + " | ".join(f(r) for r in rows) + " |")
    line("TUFS synsets", lambda r: f"{r['tufs_synsets']:,}")
    line("…we have (with words)", lambda r: f"{r['shared_synsets']:,} "
         f"({pct(r['shared_synsets'], r['tufs_synsets'])})")
    line("TUFS senses", lambda r: f"{r['tufs_senses']:,}")
    line("…same sense in ours", lambda r: f"{r['agree']:,} "
         f"({pct(r['agree'], r['tufs_senses'])})")
    line("…word only in other synsets", lambda r: f"{r['elsewhere']:,} "
         f"({pct(r['elsewhere'], r['tufs_senses'])})")
    line("…word not in ours", lambda r: f"{r['absent']:,} "
         f"({pct(r['absent'], r['tufs_senses'])})")
    line("Shared synsets, no word in common", lambda r: f"{r['disjoint']:,} "
         f"({pct(r['disjoint'], r['shared_synsets'])})")
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
