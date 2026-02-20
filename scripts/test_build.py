#!/usr/bin/env python3
"""Verify that built WN-LMF XML wordnets match the source database.

Checks that lemma counts, sense counts, and synset counts in each XML
file are consistent with the database (under the same filtering
conditions used during extraction by getwn.py).

Usage:
    test_build.py WN_DB BUILDDIR [--lang LANG ...]

Exits with code 0 if all checks pass, 1 otherwise.
"""

import argparse
import sqlite3
import sys
from collections import defaultdict as dd
from pathlib import Path

import wn
import wn.lmf
from wn.constants import REVERSE_RELATIONS


# Must match getwn.py
LANGUAGES = {
    "eng": "ntumc-en",
    "jpn": "ntumc-ja",
    "cmn": "ntumc-cmn",
    "ind": "ntumc-id",
    "zsm": "ntumc-zsm",
    "ita": "ntumc-it",
    "ces": "ntumc-cs",
}

RELATION_MAP = {
    "hype": "hypernym", "hypo": "hyponym",
    "inst": "instance_hyponym", "hasi": "instance_hypernym",
    "mprt": "mero_part", "msub": "mero_substance", "mmem": "mero_member",
    "hprt": "holo_part", "hsub": "holo_substance", "hmem": "holo_member",
    "attr": "attribute", "ants": "antonym", "sim": "similar",
    "also": "also", "enta": "entails", "caus": "causes",
    "dmnc": "domain_topic", "dmtc": "has_domain_topic",
    "dmnr": "domain_region", "dmtr": "has_domain_region",
    "dmnu": "exemplifies", "dmtu": "is_exemplified_by",
    "hasq": "restricted_by", "qant": "restricts", "eqls": "eq_synonym",
}

VALID_POS = set("nvartu")


def norm_pos(p):
    """Normalize POS codes (must match getwn.py)."""
    return {"s": "a", "z": "u"}.get(p, p or "x")


def compute_db_counts(db, lang, base_specifier=None):
    """Replicate getwn.py's extraction logic and return expected counts.

    Returns (n_entries, n_senses, n_synsets).
    """
    # ── Load words ──
    words = {}
    for wid, lemma, pos in db.execute(
        "SELECT wordid, lemma, pos FROM word WHERE lang = ?", (lang,)
    ):
        words[wid] = (lemma, pos)

    # ── Load senses ──
    senses = dd(set)
    synsets_used = set()
    for synset, wid, freq, conf in db.execute(
        "SELECT synset, wordid, freq, confidence FROM sense WHERE lang = ?",
        (lang,),
    ):
        senses[wid].add((synset, freq or 0, conf or 1.0))
        synsets_used.add(synset)

    # ── Load definitions ──
    defs = dd(list)
    for synset, d in db.execute(
        "SELECT synset, def FROM synset_def WHERE lang = ? ORDER BY sid",
        (lang,),
    ):
        defs[synset].append(d)
        synsets_used.add(synset)

    # ── Load synlinks ──
    # Note: getwn.py expands synsets_used for ALL link types, not just
    # those in RELATION_MAP, so we must do the same here.
    synlinks = dd(list)
    for s1, s2, link in db.execute(
        "SELECT synset1, synset2, link FROM synlink"
    ):
        if s1 in synsets_used or s2 in synsets_used:
            if link in RELATION_MAP:
                synlinks[s1].append((RELATION_MAP[link], s2))
            synsets_used.add(s1)
            synsets_used.add(s2)

    # ── Auto-reverse relations ──
    existing = {(s1, rel, s2)
                for s1, rels in synlinks.items() for rel, s2 in rels}
    for s1, rels in list(synlinks.items()):
        for rel_type, s2 in rels:
            rev = REVERSE_RELATIONS.get(rel_type)
            if rev and (s2, rev, s1) not in existing:
                synlinks[s2].append((rev, s1))
                existing.add((s2, rev, s1))

    # ── Base filtering ──
    if base_specifier:
        content_synsets = set()
        for wid, sense_set in senses.items():
            for synset, _f, _c in sense_set:
                content_synsets.add(synset)
        content_synsets.update(defs.keys())

        base_wn = wn.Wordnet(base_specifier)
        base_lex = base_wn.lexicons()[0]
        prefix = base_lex.id + "-"

        base_rel_set = set()
        for ss in base_wn.synsets():
            bare = ss.id[len(prefix):] if ss.id.startswith(prefix) else ss.id
            for rel_type, targets in ss.relations().items():
                for t in targets:
                    tbare = (t.id[len(prefix):]
                             if t.id.startswith(prefix) else t.id)
                    base_rel_set.add((bare, rel_type, tbare))
                    rev = REVERSE_RELATIONS.get(rel_type)
                    if rev:
                        base_rel_set.add((tbare, rev, bare))

        has_hyponym = set()
        new_synlinks = dd(list)
        for s1, rels in synlinks.items():
            for rel_type, s2 in rels:
                if (s1, rel_type, s2) not in base_rel_set:
                    new_synlinks[s1].append((rel_type, s2))
                    if rel_type == "hype" and s1 in content_synsets:
                        has_hyponym.add(s2)
        synlinks = new_synlinks

        needed = content_synsets | has_hyponym

        # Prune relations referencing removed synsets
        pruned = dd(list)
        for s1, rels in synlinks.items():
            if s1 not in needed:
                continue
            for rel_type, s2 in rels:
                if s2 in needed:
                    pruned[s1].append((rel_type, s2))
        synlinks = pruned

        synsets_used = synsets_used & needed

    # ── Filter synsets by valid POS ──
    # getwn.py uses the last character of synset ID for POS
    valid_synsets = set()
    for ss in synsets_used:
        pos = norm_pos(ss[-1])
        if pos in VALID_POS:
            valid_synsets.add(ss)

    # ── Merge entries for cmn ──
    if lang == "cmn":
        canonical, merged_senses = _merge_wordids(words, senses)
        entry_source = canonical
        sense_source = merged_senses
    else:
        entry_source = {wid: (lemma, pos, [])
                        for wid, (lemma, pos) in words.items()}
        sense_source = senses

    # ── Count entries ──
    n_entries = len(entry_source)

    # ── Count senses (only those whose synset is valid) ──
    n_senses = 0
    for wid in entry_source:
        for synset, freq, conf in sense_source.get(wid, set()):
            if synset in valid_synsets:
                n_senses += 1

    # ── Count synsets ──
    n_synsets = len(valid_synsets)

    return n_entries, n_senses, n_synsets


def _merge_wordids(words, senses):
    """Replicate getwn.py's merge_wordids for cmn."""
    groups = dd(list)
    for wid, (lemma, pos) in words.items():
        norm = lemma.replace(" ", "").replace("\u2423", "")
        groups[(norm, pos)].append(wid)

    canonical = {}
    merged_senses = {}

    for (norm, pos), wids in groups.items():
        if len(wids) < 2:
            wid = wids[0]
            canonical[wid] = (words[wid][0], pos, [])
            merged_senses[wid] = senses.get(wid, set())
            continue

        by_synsets = dd(list)
        for wid in wids:
            key = frozenset(s[0] for s in senses.get(wid, set()))
            by_synsets[key].append(wid)

        for synset_key, group_wids in by_synsets.items():
            if len(group_wids) < 2:
                wid = group_wids[0]
                canonical[wid] = (words[wid][0], pos, [])
                merged_senses[wid] = senses.get(wid, set())
                continue

            group_wids.sort(
                key=lambda w: (len(words[w][0]), words[w][0])
            )
            canon_wid = group_wids[0]
            canon_lemma = words[canon_wid][0]
            variants = [words[w][0] for w in group_wids[1:]
                        if words[w][0] != canon_lemma]

            all_senses = {}
            for wid in group_wids:
                for synset, freq, conf in senses.get(wid, set()):
                    if synset not in all_senses or freq > all_senses[synset][1]:
                        all_senses[synset] = (synset, freq, conf)

            canonical[canon_wid] = (canon_lemma, pos, variants)
            merged_senses[canon_wid] = set(all_senses.values())

    return canonical, merged_senses


def load_xml_stats(xmlpath):
    """Load an XML file and return (n_entries, n_senses, n_synsets)."""
    res = wn.lmf.load(str(xmlpath), progress_handler=None)
    lex = res["lexicons"][0]
    n_entries = len(lex["entries"])
    n_senses = sum(len(e.get("senses", [])) for e in lex["entries"])
    n_synsets = len(lex["synsets"])
    return n_entries, n_senses, n_synsets


def main():
    parser = argparse.ArgumentParser(
        description="Verify WN-LMF XML wordnets match the source database."
    )
    parser.add_argument("db", help="Path to wn-ntumc.db")
    parser.add_argument("builddir", help="Build directory with XML files")
    parser.add_argument(
        "--lang", nargs="*", default=None,
        help="Languages to test (default: all available XML files)",
    )
    parser.add_argument(
        "--base", default="omw-en:2.0",
        help="Base wordnet specifier (default: omw-en:2.0)",
    )
    args = parser.parse_args()

    builddir = Path(args.builddir)
    db = sqlite3.connect(args.db)

    langs = args.lang or [
        lang for lang in LANGUAGES
        if (builddir / f"wn-ntumc-{lang}.xml").exists()
    ]

    failures = 0
    for lang in langs:
        xmlpath = builddir / f"wn-ntumc-{lang}.xml"
        if not xmlpath.exists():
            print(f"SKIP {lang}: {xmlpath} not found")
            continue

        print(f"--- {lang} ---")
        xml_entries, xml_senses, xml_synsets = load_xml_stats(xmlpath)
        db_entries, db_senses, db_synsets = compute_db_counts(
            db, lang, args.base
        )

        ok = True

        if xml_entries != db_entries:
            print(f"  FAIL entries: XML={xml_entries} DB={db_entries} "
                  f"(diff={xml_entries - db_entries})")
            ok = False
        else:
            print(f"  OK   entries: {xml_entries}")

        if xml_senses != db_senses:
            print(f"  FAIL senses:  XML={xml_senses} DB={db_senses} "
                  f"(diff={xml_senses - db_senses})")
            ok = False
        else:
            print(f"  OK   senses:  {xml_senses}")

        if xml_synsets != db_synsets:
            print(f"  FAIL synsets: XML={xml_synsets} DB={db_synsets} "
                  f"(diff={xml_synsets - db_synsets})")
            ok = False
        else:
            print(f"  OK   synsets: {xml_synsets}")

        if not ok:
            failures += 1

    db.close()
    print()
    if failures:
        print(f"FAILED: {failures}/{len(langs)} languages had mismatches")
        sys.exit(1)
    else:
        print(f"PASSED: all {len(langs)} languages match")
        sys.exit(0)


if __name__ == "__main__":
    main()
