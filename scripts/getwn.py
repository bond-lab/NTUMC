#!/usr/bin/env python3
"""Extract wordnets from wn-ntumc.db using wn_edit.

Usage: getwn.py WN_DB OUTDIR

Produces one WN-LMF XML file per language: OUTDIR/wn-ntumc-LANG.xml
"""

import argparse
import sqlite3
import sys
from collections import defaultdict as dd
from pathlib import Path

from wn import lmf
from wn.validate import validate
from wn_edit import WordnetEditor, make_sense

# NTU-MC languages and their wordnet metadata
LANGUAGES = {
    "eng": {
        "id": "ntumc-en",
        "label": "NTU-MC English Wordnet",
        "lg": "en",
        "email": "bond@ieee.org",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    },
    "jpn": {
        "id": "ntumc-ja",
        "label": "NTU-MC Japanese Wordnet",
        "lg": "ja",
        "email": "bond@ieee.org",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    },
    "cmn": {
        "id": "ntumc-cmn",
        "label": "NTU-MC Chinese Open Wordnet",
        "lg": "cmn-Hans",
        "email": "bond@ieee.org",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    },
    "ind": {
        "id": "ntumc-id",
        "label": "NTU-MC Bahasa Wordnet Indonesia",
        "lg": "id",
        "email": "bond@ieee.org",
        "license": "https://opensource.org/licenses/MIT/",
    },
    "zsm": {
        "id": "ntumc-zsm",
        "label": "NTU-MC Bahasa Wordnet Malaysia",
        "lg": "zsm",
        "email": "bond@ieee.org",
        "license": "https://opensource.org/licenses/MIT/",
    },
    "ita": {
        "id": "ntumc-it",
        "label": "NTU-MC Italian Wordnet",
        "lg": "it",
        "email": "bond@ieee.org",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    },
    "ces": {
        "id": "ntumc-cs",
        "label": "NTU-MC Czech Wordnet",
        "lg": "cs",
        "email": "bond@ieee.org",
        "license": "https://creativecommons.org/licenses/by/4.0/",
    },
}

# Map DB link codes to WN-LMF relation types
POS_MAP = {"s": "a", "z": "u"}


def norm_pos(pos):
    """Normalize POS tag for WN-LMF."""
    return POS_MAP.get(pos, pos or "x")


RELATION_MAP = {
    "hype": "hypernym",
    "hypo": "hyponym",
    "inst": "instance_hyponym",
    "hasi": "instance_hypernym",
    "mprt": "mero_part",
    "msub": "mero_substance",
    "mmem": "mero_member",
    "hprt": "holo_part",
    "hsub": "holo_substance",
    "hmem": "holo_member",
    "attr": "attribute",
    "ants": "antonym",
    "sim": "similar",
    "also": "also",
    "enta": "entails",
    "caus": "causes",
    "dmnc": "domain_topic",
    "dmtc": "has_domain_topic",
    "dmnr": "domain_region",
    "dmtr": "has_domain_region",
    "dmnu": "exemplifies",
    "dmtu": "is_exemplified_by",
    "hasq": "restricted_by",
    "qant": "restricts",
    "eqls": "eq_synonym",
}


def extract_wordnet(db_path, lang, meta, outdir):
    """Extract a single language wordnet from the DB and write XML."""
    con = sqlite3.connect(db_path)
    c = con.cursor()

    # Collect senses: wordid -> [(synset, freq, confidence), ...]
    senses = dd(set)
    synsets_used = set()
    c.execute(
        "SELECT synset, wordid, freq, confidence FROM sense WHERE lang = ?",
        (lang,),
    )
    for synset, wid, freq, confidence in c:
        senses[wid].add((synset, freq or 0, confidence or 1.0))
        synsets_used.add(synset)

    # Collect words: [(wordid, lemma, pos), ...]
    c.execute(
        "SELECT wordid, lemma, pos FROM word WHERE lang = ?",
        (lang,),
    )
    words = {wid: (lemma, pos) for wid, lemma, pos in c}

    # Collect definitions for this language
    defs = dd(list)
    c.execute(
        "SELECT synset, def FROM synset_def WHERE lang = ? ORDER BY sid",
        (lang,),
    )
    for synset, d in c:
        defs[synset].append(d)
        synsets_used.add(synset)

    # Collect synset relations (only for synsets we use)
    synlinks = dd(list)
    c.execute("SELECT synset1, synset2, link FROM synlink")
    for s1, s2, link in c:
        if s1 in synsets_used or s2 in synsets_used:
            if link in RELATION_MAP:
                synlinks[s1].append((RELATION_MAP[link], s2))
            synsets_used.add(s1)
            synsets_used.add(s2)

    con.close()

    # Build wordnet with wn_edit
    wn_id = meta["id"]
    editor = WordnetEditor(
        create_new=True,
        lexicon_id=wn_id,
        label=meta["label"],
        language=meta["lg"],
        email=meta["email"],
        license=meta["license"],
        version="1.0",
    )

    # Add synsets
    for synset in sorted(synsets_used):
        pos = norm_pos(synset[-1])
        if pos not in "nvartu":
            continue
        defn = "; ".join(defs[synset]) if synset in defs else None
        editor.create_synset(
            pos=pos,
            synset_id=f"{wn_id}-{synset}",
            definition=defn,
            ili="",
        )

    # Add synset relations (after all synsets exist)
    for synset in synlinks:
        source_id = f"{wn_id}-{synset}"
        if editor.get_synset(source_id) is None:
            continue
        for rel_type, target in synlinks[synset]:
            target_id = f"{wn_id}-{target}"
            if editor.get_synset(target_id) is None:
                continue
            editor.add_synset_relation(
                source_id, target_id, rel_type, validate=False
            )

    # Add entries and senses
    entry_num = 0
    for wid in sorted(senses.keys()):
        if wid not in words:
            continue
        lemma, pos = words[wid]
        pos = norm_pos(pos)
        entry_id = f"w{entry_num}"
        entry_num += 1
        entry = editor.create_entry(lemma, pos, entry_id=entry_id)
        sense_num = 0
        for synset, freq, confidence in sorted(senses[wid]):
            ss_id = f"{wn_id}-{synset}"
            if editor.get_synset(ss_id) is None:
                continue
            sense_id = f"{wn_id}-{synset}-{entry_id}"
            sense = make_sense(sense_id, ss_id)
            entry["senses"].append(sense)
            sense_num += 1

    # Export
    outfile = outdir / f"wn-ntumc-{lang}.xml"
    editor.export(str(outfile))
    stats = editor.stats()
    return outfile, stats


def validate_xml(xmlpath, out):
    """Validate a WN-LMF XML file and write results to out."""
    res = lmf.load(str(xmlpath))
    lex = res["lexicons"][0]
    results = validate(lex, progress_handler=None)
    has_issues = False
    for code in sorted(results):
        check = results[code]
        items = check.get("items", {})
        if not items:
            continue
        has_issues = True
        message = check.get("message", "")
        out.write(f"  {code} ({len(items)}): {message}\n")
        for item_id, detail in items.items():
            if detail:
                out.write(f"    {item_id}: {detail}\n")
            else:
                out.write(f"    {item_id}\n")
    return has_issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("db", help="Path to wn-ntumc.db")
    parser.add_argument("outdir", help="Output directory for XML files")
    parser.add_argument(
        "--lang",
        nargs="*",
        help="Languages to extract (default: all)",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Write validation report to FILE",
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    langs = args.lang if args.lang else list(LANGUAGES.keys())

    report = open(args.output_file, "w") if args.output_file else None

    for lang in langs:
        if lang not in LANGUAGES:
            print(f"  WARNING: unknown language {lang}, skipping", file=sys.stderr)
            continue
        outfile, stats = extract_wordnet(args.db, lang, LANGUAGES[lang], outdir)
        summary = (
            f"  {lang}: {stats['synsets']} synsets, "
            f"{stats['entries']} entries, "
            f"{stats['senses']} senses -> {outfile.name}"
        )
        print(summary)

        if report:
            report.write(f"\n=== {lang} ({outfile.name}) ===\n")
            report.write(f"{summary.strip()}\n")
            if not validate_xml(outfile, report):
                report.write("  OK\n")

    if report:
        report.close()
        print(f"  Validation report: {args.output_file}")


if __name__ == "__main__":
    main()
