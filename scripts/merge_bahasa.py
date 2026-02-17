#!/usr/bin/env python3
"""Merge NTU-MC wordnet XML with Bahasa Wordnet tab data.

Usage:
    merge_bahasa.py NTUMC_XML TAB_DIR [-o OUTPUT]

Takes a WN-LMF XML file produced by getwn.py (for ind or zsm) and merges
it with data from the Bahasa Wordnet tab files:

  - wn-msa-all.tab: confidence scores used to filter senses
    (keep only confidence > 0.85 or senses not in tab data)
  - wn-ind-def.tab: Indonesian definitions added to synsets

The tab data is from https://github.com/bond-lab/Bahasa-Wordnet
"""

import argparse
import datetime
import sys
from collections import defaultdict
from pathlib import Path

from wn import lmf

# Confidence map for status codes in wn-msa-all.tab
STATUS_CONF = {"Y": 1.0, "O": 0.9, "M": 0.6, "L": 0.4, "X": 0}
MIN_CONFIDENCE = 0.85

CITATION = (
    "Nurril Hirfana Mohamed Noor, Suerya Sapuan and Francis Bond. 2011."
    " Creating the open Wordnet Bahasa."
    " In Proceedings of the 25th Pacific Asia Conference on Language,"
    " Information and Computation (PACLIC 25). pp 258\u2013267. Singapore."
)

# Per-language output metadata (keyed by WN-LMF language code)
LANG_META = {
    "id": {
        "id": "wnb-id",
        "label": "Wordnet Bahasa (Indonesian)",
        "license": "https://opensource.org/licenses/MIT/",
        "filename": "wn-bahasa-id.xml",
    },
    "zsm": {
        "id": "wnb-zsm",
        "label": "Wordnet Bahasa (Malay)",
        "license": "https://opensource.org/licenses/MIT/",
        "filename": "wn-bahasa-zsm.xml",
    },
}


def load_tab_senses(tab_dir, lang):
    """Load wn-msa-all.tab and return {(synset, lemma): confidence} for lang.

    Tab file language codes: B=both ind+zsm, I=ind only, M=zsm only.
    """
    path = Path(tab_dir) / "wn-msa-all.tab"
    if lang == "id":
        db_lang = "ind"
        accept = ("B", "I")
    elif lang == "zsm":
        db_lang = "zsm"
        accept = ("B", "M")
    else:
        print(f"  WARNING: unsupported language {lang}, skipping tab filter",
              file=sys.stderr)
        return {}

    conf = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            ss, lng, status, lemma = parts
            if lng in accept:
                c = STATUS_CONF.get(status, 0.1)
                # Keep highest confidence if same pair appears multiple times
                key = (ss, lemma)
                if key not in conf or c > conf[key]:
                    conf[key] = c
            elif lng == "B":
                # B applies to both languages
                pass  # already handled above
    return conf


def load_tab_defs(tab_dir):
    """Load wn-ind-def.tab and return {synset: definition}."""
    path = Path(tab_dir) / "wn-ind-def.tab"
    if not path.exists():
        return {}
    defs = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            ss, typ, dfn = parts
            if typ == "ind:def":
                defs[ss] = dfn.strip().strip(";")
    return defs


def strip_prefix(synset_id, prefix):
    """Strip lexicon prefix from synset ID: 'ntumc-id-00001740-a' -> '00001740-a'."""
    if synset_id.startswith(prefix + "-"):
        return synset_id[len(prefix) + 1:]
    return synset_id


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("xml", help="WN-LMF XML file from getwn.py")
    parser.add_argument("tab_dir", help="Directory with wn-msa-all.tab and wn-ind-def.tab")
    parser.add_argument("-o", "--output", help="Output XML file (default: auto from language)")
    parser.add_argument("--version", default=None,
                        help="Release version (default: today's date)")
    args = parser.parse_args()

    # Load XML
    print(f"  Loading {args.xml}")
    data = lmf.load(args.xml)
    lex = data["lexicons"][0]
    lang = lex["language"]
    old_prefix = lex["id"]  # e.g. "ntumc-id"

    if lang not in LANG_META:
        print(f"  ERROR: unsupported language {lang}", file=sys.stderr)
        sys.exit(1)
    meta = LANG_META[lang]
    new_prefix = meta["id"]  # e.g. "wnb-id"

    print(f"  Lexicon: {old_prefix} ({lang}) -> {new_prefix}")
    print(f"  Input: {len(lex['entries'])} entries, {len(lex['synsets'])} synsets")

    # Reprefix all IDs from old_prefix to new_prefix
    def reprefix(s):
        if s and s.startswith(old_prefix + "-"):
            return new_prefix + s[len(old_prefix):]
        return s

    for ss in lex["synsets"]:
        ss["id"] = reprefix(ss["id"])
        for rel in ss.get("relations", []):
            rel["target"] = reprefix(rel["target"])
        if "members" in ss:
            ss["members"] = [reprefix(m) for m in ss["members"]]
    for entry in lex.get("entries", []):
        for sense in entry.get("senses", []):
            sense["id"] = reprefix(sense["id"])
            sense["synset"] = reprefix(sense["synset"])

    # Update lexicon metadata
    lex["id"] = new_prefix
    lex["label"] = meta["label"]
    lex["license"] = meta["license"]
    lex["citation"] = CITATION
    lex["version"] = args.version or datetime.date.today().isoformat()

    prefix = new_prefix  # use new prefix for the rest of the script

    # Load tab data
    tab_conf = load_tab_senses(args.tab_dir, lang)
    print(f"  Loaded {len(tab_conf)} sense confidence scores from wn-msa-all.tab")

    tab_defs = load_tab_defs(args.tab_dir) if lang == "id" else {}
    if tab_defs:
        print(f"  Loaded {len(tab_defs)} definitions from wn-ind-def.tab")

    # Build set of synsets referenced by kept senses (for cleanup)
    kept_synsets = set()
    removed_senses = 0
    kept_senses = 0
    empty_entries = 0

    # Filter senses by confidence
    for entry in lex["entries"]:
        lemma = entry["lemma"]["writtenForm"]
        new_senses = []
        for sense in entry.get("senses", []):
            ss_id = sense["synset"]
            bare_ss = strip_prefix(ss_id, prefix)
            key = (bare_ss, lemma)
            if key in tab_conf:
                if tab_conf[key] >= MIN_CONFIDENCE:
                    new_senses.append(sense)
                    kept_synsets.add(ss_id)
                    kept_senses += 1
                else:
                    removed_senses += 1
            else:
                # Not in tab data — keep (hand-made from DB)
                new_senses.append(sense)
                kept_synsets.add(ss_id)
                kept_senses += 1
        entry["senses"] = new_senses
        if not new_senses:
            empty_entries += 1

    # Remove entries with no senses
    orig_entries = len(lex["entries"])
    lex["entries"] = [e for e in lex["entries"] if e.get("senses")]

    print(f"  Senses: kept {kept_senses}, removed {removed_senses}")
    print(f"  Entries: {orig_entries} -> {len(lex['entries'])} "
          f"({empty_entries} empty removed)")

    # Add definitions from tab file
    defs_added = 0
    synset_by_id = {ss["id"]: ss for ss in lex["synsets"]}
    for bare_ss, dfn in tab_defs.items():
        ss_id = f"{prefix}-{bare_ss}"
        ss = synset_by_id.get(ss_id)
        if ss is None:
            continue
        existing = ss.get("definitions", [])
        if not existing:
            ss["definitions"] = [{"text": dfn, "meta": None}]
            defs_added += 1
    print(f"  Definitions added: {defs_added}")

    # Update synset members to reflect removed senses
    kept_sense_ids = set()
    for entry in lex["entries"]:
        for sense in entry.get("senses", []):
            kept_sense_ids.add(sense["id"])
    for ss in lex["synsets"]:
        if "members" in ss:
            ss["members"] = [m for m in ss["members"] if m in kept_sense_ids]

    # Remove synsets with no senses and no definitions (they exist in the
    # base wordnet declared via <Requires>)
    has_def = {ss["id"] for ss in lex["synsets"] if ss.get("definitions")}
    needed_synsets = kept_synsets | has_def
    orig_synsets = len(lex["synsets"])
    lex["synsets"] = [ss for ss in lex["synsets"] if ss["id"] in needed_synsets]
    removed_synsets = orig_synsets - len(lex["synsets"])
    if removed_synsets:
        # Also strip relations pointing to removed synsets
        for ss in lex["synsets"]:
            if ss.get("relations"):
                ss["relations"] = [
                    r for r in ss["relations"] if r["target"] in needed_synsets
                ]
        print(f"  Synsets: {orig_synsets} -> {len(lex['synsets'])} "
              f"({removed_synsets} empty removed)")

    # Export
    if args.output:
        outpath = args.output
    else:
        outpath = str(Path(args.xml).parent / meta["filename"])
    lmf.dump(data, outpath)
    print(f"  Written to {outpath}")
    print(f"  Final: {len(lex['entries'])} entries, "
          f"{len(lex['synsets'])} synsets")


if __name__ == "__main__":
    main()
