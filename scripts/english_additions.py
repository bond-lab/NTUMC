#!/usr/bin/env python3
"""Cut ntumc-en down to what NTU-MC added, for a Cygnet build.

    .venv/bin/python scripts/english_additions.py NTUMC_EN_MIN.xml OUT.xml

ntumc-en is the whole Open English Wordnet with our changes.  Cygnet
takes the Open English Wordnet itself as its English base, so beside it
it needs only our additions: the senses, entries and synsets whose ids
begin ``ntumc-en-``.  A synset of the base that an added sense is in is
kept as a stub (its ILI, or its definition if it has no ILI), so that
Cygnet can find the concept.  Relations to anything left out are dropped.
"""

import argparse
import logging
import xml.etree.ElementTree as etree
from pathlib import Path

OWN = "ntumc-en-"
HEAD = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE LexicalResource SYSTEM '
        '"https://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd">\n')
log = logging.getLogger("english_additions")


def cut(root: etree.Element) -> tuple[int, int, int]:
    """Remove from a lexicon all but the additions (in place).

    Args:
        root: the LexicalResource

    Returns:
        How many entries, senses and synsets are left.
    """
    lexicon = root.find("Lexicon")
    used = set()
    senses = 0
    for entry in lexicon.findall("LexicalEntry"):
        for sense in entry.findall("Sense"):
            if not sense.get("id").startswith(OWN):
                entry.remove(sense)
                continue
            for child in sense.findall("SenseRelation"):
                sense.remove(child)
            used.add(sense.get("synset"))
            senses += 1
        if entry.find("Sense") is None:
            lexicon.remove(entry)
    kept = {s.get("id") for s in lexicon.findall("Synset")
            if s.get("id") in used or s.get("id").startswith(OWN)}
    for synset in lexicon.findall("Synset"):
        if synset.get("id") not in kept:
            lexicon.remove(synset)
            continue
        synset.attrib.pop("members", None)
        stub = not synset.get("id").startswith(OWN)
        for child in list(synset):
            gone = child.tag == "SynsetRelation" and child.get("target") not in kept
            if gone or (stub and (child.tag != "Definition" or synset.get("ili"))):
                synset.remove(child)
    for other in lexicon.findall("SyntacticBehaviour"):
        lexicon.remove(other)
    return len(lexicon.findall("LexicalEntry")), senses, len(kept)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="ntumc-en (the minimal lexicon)")
    parser.add_argument("out", type=Path, help="the file to write")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    etree.register_namespace("dc", "https://globalwordnet.github.io/schemas/dc/")
    tree = etree.parse(str(args.source))
    log.info("Kept %d entries, %d senses, %d synsets", *cut(tree.getroot()))
    etree.indent(tree)
    with args.out.open("w", encoding="utf-8") as f:
        f.write(HEAD)
        tree.write(f, encoding="unicode")
        f.write("\n")


if __name__ == "__main__":
    main()
