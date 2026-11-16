#!/usr/bin/env python3
"""Split the Chinese token 印度菜 (cmn sid 60417) into 印度 and 菜.

    .venv/bin/python scripts/2026-11/split_indian_food.py build/cmn.db [--apply]

Indian food (90000063-n) is withdrawn from omw-ntumc as the sum of its
parts (Francis Bond, 2026-11-16), and this was its one Chinese tag, on
a single token.  The token becomes two words; the concept is retagged
as India (08900535-n) and a new concept tags 菜 as cuisine
(07557434-n), as elsewhere in the corpus.  The later words of the
sentence move up by one.  No sentence, word or concept link and no
sentiment refers to the sentence.

Without --apply nothing is written.  Running it twice changes nothing more.
"""

import argparse
import logging
import sqlite3
from pathlib import Path

SID, WID, CID = 60417, 6, 4
USER = "fcbond"
NOTE = "split from 印度菜 (Indian food, 90000063-n, withdrawn 2026-11-16)"

log = logging.getLogger("split")


def split(con: sqlite3.Connection) -> bool:
    """Split the token and retag it; the caller commits or rolls back.

    Args:
        con: the open Chinese corpus database

    Returns:
        Whether anything was changed (False if the token is already split)
    """
    row = con.execute("SELECT word, cfrom FROM word WHERE sid = ? AND wid = ?",
                      (SID, WID)).fetchone()
    if row != ("印度菜", 7):
        return False
    later = [w for (w,) in con.execute(
        "SELECT wid FROM word WHERE sid = ? AND wid > ? ORDER BY wid DESC", (SID, WID))]
    for wid in later:
        con.execute("UPDATE word SET wid = ? WHERE sid = ? AND wid = ?", (wid + 1, SID, wid))
        con.execute("UPDATE cwl SET wid = ? WHERE sid = ? AND wid = ?", (wid + 1, SID, wid))
    con.execute("UPDATE word SET word = '印度', lemma = '印度', cto = 9, usrname = ? "
                "WHERE sid = ? AND wid = ?", (USER, SID, WID))
    con.execute("INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, usrname) "
                "VALUES (?, ?, '菜', 'NN', '菜', 9, 10, ?)", (SID, WID + 1, USER))
    con.execute("UPDATE concept SET clemma = '印度', tag = '08900535-n', comment = ?, "
                "usrname = ? WHERE sid = ? AND cid = ?", (NOTE, USER, SID, CID))
    (cid,) = con.execute("SELECT max(cid) + 1 FROM concept WHERE sid = ?", (SID,)).fetchone()
    con.execute("INSERT INTO concept (sid, cid, clemma, tag, comment, usrname) "
                "VALUES (?, ?, '菜', '07557434-n', ?, ?)", (SID, cid, NOTE, USER))
    con.execute("INSERT INTO cwl (sid, wid, cid, usrname) VALUES (?, ?, ?, ?)",
                (SID, WID + 1, cid, USER))
    return True


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path, help="the Chinese corpus database")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    con = sqlite3.connect(args.db)
    try:
        changed = split(con)
        if args.apply:
            con.commit()
        else:
            con.rollback()
    finally:
        con.close()
    log.info("%s%s", "split" if changed else "nothing to do",
             "" if args.apply or not changed else " (not written)")


if __name__ == "__main__":
    main()
