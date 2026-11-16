#!/usr/bin/env python3
"""Retag English for Francis Bond's rulings of 2026-11-16 on senses held from ntumc-en.

    .venv/bin/python scripts/2026-11/retag_held_senses.py build/eng.db [--apply]

* "at all" was on a synset the Open English Wordnet dropped (00008007-r,
  wholly): it is now "in the slightest degree" (00056729-r, i18477).
  In sid 47263 it was part of "at all costs", which has its own tag
  there (00153116-r, i19171), so that concept is dropped.
* The wordnet keeps "Heaven" and "Tang dynasty", not the lower-case
  forms: the concepts' lemmas follow.

Without --apply nothing is written.  Running it twice changes nothing more.
"""

import argparse
import logging
import sqlite3
from pathlib import Path

USER = "fcbond"
DROP = [(47263, 8, "at all", "00008007-r")]
TAG = [(49410, 23, "at all", "00008007-r", "00056729-r"),
       (110619, 14, "at all", "00008007-r", "00056729-r")]
LEMMA = [("05627785-n", "heaven", "Heaven"), ("08158920-n", "tang dynasty", "Tang dynasty")]

log = logging.getLogger("retag")


def retag(con: sqlite3.Connection) -> dict[str, int]:
    """Make the changes; the caller commits or rolls back.

    Args:
        con: the open English corpus database

    Returns:
        How many concepts were ``dropped``, ``retagged`` and ``renamed``
    """
    counts = {"dropped": 0, "retagged": 0, "renamed": 0}
    for sid, cid, lemma, tag in DROP:
        cur = con.execute("DELETE FROM concept WHERE sid = ? AND cid = ? AND clemma = ? "
                          "AND tag = ?", (sid, cid, lemma, tag))
        if cur.rowcount:
            con.execute("DELETE FROM cwl WHERE sid = ? AND cid = ?", (sid, cid))
        counts["dropped"] += cur.rowcount
    for sid, cid, lemma, old, new in TAG:
        cur = con.execute("UPDATE concept SET tag = ?, usrname = ? WHERE sid = ? AND cid = ? "
                          "AND clemma = ? AND tag = ?", (new, USER, sid, cid, lemma, old))
        counts["retagged"] += cur.rowcount
    for tag, old, new in LEMMA:
        cur = con.execute("UPDATE concept SET clemma = ?, usrname = ? WHERE tag = ? "
                          "AND clemma = ?", (new, USER, tag, old))
        counts["renamed"] += cur.rowcount
    return counts


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path, help="the English corpus database")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    con = sqlite3.connect(args.db)
    try:
        counts = retag(con)
        if args.apply:
            con.commit()
        else:
            con.rollback()
    finally:
        con.close()
    log.info("%s%s", counts, "" if args.apply else " (not written)")


if __name__ == "__main__":
    main()
