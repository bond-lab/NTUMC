#!/usr/bin/env python3
"""Write the full-width digits and Latin letters of concept lemmas half-width.

    .venv/bin/python scripts/2026-11/halfwidth_lemmas.py build/cmn.db [--apply]

A concept's lemma (``concept.clemma``) is what is looked up in the
wordnet, and the wordnets write digits and Latin letters half-width
(2, 1月, 卡拉OK), while the Chinese and Japanese text often has them
full-width (２, １月).  The lemma is changed; the words of the sentence
are not.  Francis Bond suggested this on 2026-11-17, when the lemmas
were found not to match the wordnets.

Without --apply nothing is written.  Running it twice changes nothing more.
"""

import argparse
import logging
import sqlite3
from pathlib import Path

# full-width digits and Latin letters, and their half-width forms
WIDE = "".join(chr(c) for r in (range(0xFF10, 0xFF1A), range(0xFF21, 0xFF3B),
                                range(0xFF41, 0xFF5B)) for c in r)
HALF = str.maketrans(WIDE, "".join(chr(ord(c) - 0xFEE0) for c in WIDE))

log = logging.getLogger("halfwidth")


def halfwidth(lemma: str) -> str:
    """A lemma with its full-width digits and Latin letters half-width."""
    return lemma.translate(HALF)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("db", type=Path, help="a corpus database")
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    con = sqlite3.connect(args.db)
    rows = [(sid, cid, lemma) for sid, cid, lemma in con.execute(
        "SELECT sid, cid, clemma FROM concept WHERE clemma IS NOT NULL")
        if halfwidth(lemma) != lemma]
    log.info("%s: %d concept lemmas have full-width digits or letters, e.g. %s", args.db.name,
             len(rows), ", ".join(sorted({lemma for _, _, lemma in rows})[:8]))
    if args.apply:
        with con:
            con.executemany("UPDATE concept SET clemma = ? WHERE sid = ? AND cid = ?",
                            [(halfwidth(lemma), sid, cid) for sid, cid, lemma in rows])
        log.info("Changed %d lemmas", len(rows))
    con.close()


if __name__ == "__main__":
    main()
