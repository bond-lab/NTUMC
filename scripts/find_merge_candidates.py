#!/usr/bin/env python3
"""Find lemmas that differ only by whitespace/hyphens and share identical senses.

Usage:
    find_merge_candidates.py WN_DB LANG [LANG ...]

These are candidates for merging into a single LexicalEntry with variant Forms.
"""

import argparse
import sqlite3
import sys
from collections import defaultdict


def normalize_lemma(lemma, lang):
    """Normalize a lemma for comparison, removing whitespace and hyphens."""
    if lang in ("cmn", "yue", "jpn"):
        return lemma.replace(" ", "").replace("\u2423", "")
    else:
        return lemma.replace("-", "").replace(" ", "").lower()


def find_merge_candidates(db_path, lang):
    """Find groups of wordids with identical sense sets and matching normalized lemmas.

    Returns list of dicts:
        {"norm": str, "pos": str, "words": [(wordid, lemma), ...], "synsets": set}
    """
    db = sqlite3.connect(db_path)

    words = {}  # wordid -> (lemma, pos)
    word_senses = defaultdict(set)  # wordid -> {synset, ...}

    for wid, lemma, pos in db.execute(
        "SELECT wordid, lemma, pos FROM word WHERE lang = ?", (lang,)
    ):
        words[wid] = (lemma, pos)

    for synset, wid in db.execute(
        "SELECT synset, wordid FROM sense WHERE lang = ?", (lang,)
    ):
        if wid in words:
            word_senses[wid].add(synset)

    db.close()

    # Group by (normalized_lemma, pos)
    groups = defaultdict(list)
    for wid, (lemma, pos) in words.items():
        norm = normalize_lemma(lemma, lang)
        groups[(norm, pos)].append(wid)

    # Find groups where multiple wordids have identical sense sets
    candidates = []
    for (norm, pos), wids in sorted(groups.items()):
        if len(wids) < 2:
            continue
        by_senses = defaultdict(list)
        for wid in wids:
            key = frozenset(word_senses.get(wid, set()))
            if key:  # skip words with no senses
                by_senses[key].append(wid)

        for sense_set, matching_wids in by_senses.items():
            if len(matching_wids) < 2:
                continue
            candidates.append({
                "norm": norm,
                "pos": pos,
                "words": [(wid, words[wid][0]) for wid in matching_wids],
                "synsets": sense_set,
            })

    return candidates


def main():
    parser = argparse.ArgumentParser(
        description="Find lemmas that differ only by whitespace/hyphens "
        "and share identical senses."
    )
    parser.add_argument("db", help="Path to wordnet SQLite database")
    parser.add_argument("langs", nargs="+", help="Language code(s) to check")
    args = parser.parse_args()

    for lang in args.langs:
        candidates = find_merge_candidates(args.db, lang)
        print(f"=== {lang} ({len(candidates)} merge candidates) ===")
        for c in candidates:
            forms = " | ".join(lemma for _, lemma in c["words"])
            synsets = sorted(c["synsets"])[:3]
            more = f" +{len(c['synsets']) - 3} more" if len(c["synsets"]) > 3 else ""
            print(
                f"  {c['pos']}  {forms:60s}  "
                f"({len(c['synsets'])} senses: {', '.join(synsets)}{more})"
            )
        print()


if __name__ == "__main__":
    main()
