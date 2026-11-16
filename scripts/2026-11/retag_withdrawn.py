#!/usr/bin/env python3
"""Retag the corpus for concepts withdrawn from omw-ntumc on 2026-11-16.

    .venv/bin/python scripts/2026-11/retag_withdrawn.py build/ [--apply]

Francis Bond's rulings (omw-ntumc data/withdrawn.tsv):

* "In the middle" (80001218-x) is not a concept: its tags are dropped
  and "middle" is tagged, as a place (08523483-n, i81841) or as a time
  (15266685-n, i117476).
* Chilli Crab (90000014-n) is chilli crab (80002015-n).
* Hokkien the language (80001020-n) is Min (06930633-n, i72992).
* Indian food (90000063-n) is the sum of its parts.  In Indonesian
  both words already have a tag of their own, so the tag is dropped.
  The one Chinese tag is on the single token 印度菜 and is left for a
  person.

Without --apply nothing is written.  The databases' triggers log each
change.  Running it twice changes nothing more.
"""

import argparse
import logging
import sqlite3
from pathlib import Path

USER = "fcbond"
MOVE = {"90000014-n": "80002015-n", "80001020-n": "06930633-n"}
# (lang, sid, cid of "middle") -> its tag
MIDDLE = {("eng", 47409, 1): "08523483-n", ("eng", 110354, 1): "15266685-n"}
# lang -> tags whose concepts are dropped
DROP = {"eng": ["80001218-x"], "ind": ["90000063-n"]}

log = logging.getLogger("retag")


def retag(con: sqlite3.Connection, lang: str) -> dict[str, int]:
    """Make the changes for one language's corpus database.

    Args:
        con: the open database; the caller commits or rolls back
        lang: its language, ``eng``, ``cmn`` or ``ind``

    Returns:
        How many concepts were ``moved`` to another tag, ``set`` (the
        tags of "middle") and ``dropped``
    """
    counts = {"moved": 0, "set": 0, "dropped": 0}
    for old, new in MOVE.items():
        rows = con.execute("SELECT sid, cid, tags FROM concept WHERE tag = ?", (old,)).fetchall()
        for sid, cid, tags in rows:
            con.execute("UPDATE concept SET tag = ?, tags = ?, usrname = ? WHERE sid = ? AND cid = ?",
                        (new, (tags or "").replace(old, new) or None, USER, sid, cid))
        counts["moved"] += len(rows)
    for (where, sid, cid), tag in MIDDLE.items():
        if where != lang:
            continue
        cur = con.execute("UPDATE concept SET tag = ?, usrname = ? WHERE sid = ? AND cid = ? "
                          "AND clemma = 'middle' AND tag != ?", (tag, USER, sid, cid, tag))
        counts["set"] += cur.rowcount
    for tag in DROP.get(lang, []):
        rows = con.execute("SELECT sid, cid FROM concept WHERE tag = ?", (tag,)).fetchall()
        for sid, cid in rows:
            con.execute("DELETE FROM cwl WHERE sid = ? AND cid = ?", (sid, cid))
            con.execute("DELETE FROM concept WHERE sid = ? AND cid = ?", (sid, cid))
        counts["dropped"] += len(rows)
    return counts


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dbdir", type=Path, help="directory with eng.db, cmn.db and ind.db")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    for lang in ("eng", "cmn", "ind"):
        con = sqlite3.connect(args.dbdir / f"{lang}.db")
        try:
            counts = retag(con, lang)
            if args.apply:
                con.commit()
            else:
                con.rollback()
        finally:
            con.close()
        log.info("%s: %s%s", lang, counts, "" if args.apply else " (not written)")


if __name__ == "__main__":
    main()
