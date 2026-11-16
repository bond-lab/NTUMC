#!/usr/bin/env python3
"""Retag concepts whose synset the Open English Wordnet merged into another.

    .venv/bin/python scripts/2026-11/retag_oewn_merges.py build/eng.db [--apply]

OEWN 2025+ dropped 308 Princeton WordNet synsets; its deprecation list
names the synset that took the place of 158.  oewn-merges.tsv, beside
this script, has those of them that the corpus is tagged with, where
the new synset is still in OEWN and has the same part of speech (tags
as in the corpus: Princeton WordNet 3.0 offsets).  A concept tagged
with the old synset gets the new one, in ``tag`` and in the candidates
in ``tags``; who tagged it is not changed.

Francis Bond asked for this on 2026-11-16, for the English lexicon
ntumc-en, which is built on OEWN.

Without --apply nothing is written.  Running it twice changes nothing more.
"""

import argparse
import csv
import logging
import sqlite3
from pathlib import Path

MERGES = Path(__file__).with_name("oewn-merges.tsv")

log = logging.getLogger("retag")


def retag(con: sqlite3.Connection, merges: dict[str, str]) -> int:
    """Give each concept on a merged synset the synset that took its place.

    Args:
        con: the open corpus database; the caller commits or rolls back
        merges: old tag -> new tag

    Returns:
        How many concepts were retagged
    """
    done = 0
    for old, new in merges.items():
        rows = con.execute("SELECT sid, cid, tags FROM concept WHERE tag = ?", (old,)).fetchall()
        for sid, cid, tags in rows:
            con.execute("UPDATE concept SET tag = ?, tags = ? WHERE sid = ? AND cid = ?",
                        (new, tags.replace(old, new) if tags else tags, sid, cid))
        done += len(rows)
    return done


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path, help="a corpus database")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    with MERGES.open(newline="") as f:
        merges = {r["old_tag"]: r["new_tag"]
                  for r in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)}
    con = sqlite3.connect(args.db)
    try:
        done = retag(con, merges)
        if args.apply:
            con.commit()
        else:
            con.rollback()
    finally:
        con.close()
    log.info("%d concepts retagged%s", done, "" if args.apply else " (not written)")


if __name__ == "__main__":
    main()
