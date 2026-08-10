#!/usr/bin/env python3
"""Find lemmas that differ only by whitespace/hyphens and share identical senses.

Usage:
    find_merge_candidates.py WN_DB LANG [LANG ...]
    find_merge_candidates.py wordnet.xml [wordnet.xml.gz]

Accepts either a wordnet SQLite database (with language codes) or
WN-LMF XML files (plain or gzipped).  These are candidates for merging
into a single LexicalEntry with variant Forms.
"""

import argparse
import gzip
import sqlite3
from collections import defaultdict
from pathlib import Path

from wn import lmf


def normalize_lemma(lemma, lang):
    """Normalize a lemma for comparison, removing whitespace and hyphens."""
    if lang in ("cmn", "yue", "jpn"):
        return lemma.replace(" ", "").replace("\u2423", "")
    else:
        return lemma.replace("-", "").replace(" ", "").lower()


def _group_and_match(words, word_senses, lang):
    """Core logic: group by normalized lemma+pos, find identical-sense groups.

    Args:
        words: dict of id -> (lemma, pos)
        word_senses: dict of id -> {synset, ...}
        lang: language code (for normalization)

    Returns list of candidate dicts.
    """
    groups = defaultdict(list)
    for wid, (lemma, pos) in words.items():
        norm = normalize_lemma(lemma, lang)
        groups[(norm, pos)].append(wid)

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


def find_merge_candidates_db(db_path, lang):
    """Find merge candidates from an NTU-MC SQLite database."""
    db = sqlite3.connect(db_path)

    words = {}
    word_senses = defaultdict(set)

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
    return _group_and_match(words, word_senses, lang)


def find_merge_candidates_xml(xml_path):
    """Find merge candidates from a WN-LMF XML file (plain or gzipped)."""
    xml_path = Path(xml_path)
    if xml_path.suffix == ".gz":
        with gzip.open(xml_path, "rt", encoding="utf-8") as f:
            text = f.read()
        # lmf.load needs a file path; decompress to a temp path
        plain = xml_path.with_suffix("")
        plain.write_text(text, encoding="utf-8")
        data = lmf.load(str(plain))
        plain.unlink()
    else:
        data = lmf.load(str(xml_path))

    results = []
    for lex in data["lexicons"]:
        lang = lex["language"]

        words = {}
        word_senses = defaultdict(set)

        for entry in lex.get("entries", []):
            eid = entry["id"]
            lemma = entry["lemma"]["writtenForm"]
            pos = entry["lemma"]["partOfSpeech"]
            words[eid] = (lemma, pos)
            for sense in entry.get("senses", []):
                word_senses[eid].add(sense["synset"])

        candidates = _group_and_match(words, word_senses, lang)
        results.append((lang, lex.get("label", xml_path.name), candidates))

    return results


def print_candidates(label, candidates):
    """Print merge candidates in a readable format."""
    print(f"=== {label} ({len(candidates)} merge candidates) ===")
    for c in candidates:
        forms = " | ".join(lemma for _, lemma in c["words"])
        synsets = sorted(c["synsets"])[:3]
        more = f" +{len(c['synsets']) - 3} more" if len(c["synsets"]) > 3 else ""
        print(
            f"  {c['pos']}  {forms:60s}  "
            f"({len(c['synsets'])} senses: {', '.join(synsets)}{more})"
        )
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Find lemmas that differ only by whitespace/hyphens "
        "and share identical senses."
    )
    parser.add_argument(
        "source",
        help="Path to wordnet SQLite database or WN-LMF XML file (.xml or .xml.gz)",
    )
    parser.add_argument(
        "langs", nargs="*",
        help="Language code(s) to check (required for DB input, ignored for XML)",
    )
    args = parser.parse_args()

    source = Path(args.source)
    is_xml = source.suffix in (".xml", ".gz") or source.name.endswith(".xml.gz")

    if is_xml:
        for lang, label, candidates in find_merge_candidates_xml(args.source):
            print_candidates(f"{lang} — {label}", candidates)
    else:
        if not args.langs:
            parser.error("language code(s) required for database input")
        for lang in args.langs:
            candidates = find_merge_candidates_db(args.source, lang)
            print_candidates(lang, candidates)


if __name__ == "__main__":
    main()
