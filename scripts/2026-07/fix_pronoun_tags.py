#!/usr/bin/env python3
"""Retag corpus tokens after the pronoun fixes in fixwn.py (ff224b3).

fixwn.py split "either" out of the both synset (77000076-a) and removed
哪 'which' from the distal determiner (77000079-a).  Tokens tagged with
the old synsets now point to senses their lemma no longer has.  Each
token below was checked by hand in context:

  either, universal (on either side = each of two)  -> 77000141-a
  either, elective (take up either side)            -> 77000142-a
  either, pronoun (either of these)                 -> 77000074-n
  either ... or (coordinator, as elsewhere)         -> x
  哪 'which', interrogative / free choice            -> 77000091-a

Safety at apply time, per token: the concept must still have the
expected lemma and old tag, and a synset target must exist in
wn-ntumc.db.  Anything else is skipped and logged, so the script is
idempotent and safe after renumbering (fix_cmn_sids.py, fix_eng_pos.py).
Triggers are left on, so changes are recorded in concept_log where the
database has one.

Usage:
    .venv/bin/python scripts/2026-07/fix_pronoun_tags.py --dry-run
    .venv/bin/python scripts/2026-07/fix_pronoun_tags.py --fix
"""

import argparse
import logging
import sqlite3
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"

BOTH, THAT = "77000076-a", "77000079-a"
EITHER_UNIV, EITHER_ELEC, EITHER_PRON = "77000141-a", "77000142-a", "77000074-n"
WHICH = "77000091-a"

# (lang, sid, cid, lemma, old tag, new tag)
RETAGS = [
    # universal either: on either side, at either end, by either shoulder
    ("eng", 13629, 18, "either", BOTH, EITHER_UNIV),
    ("eng", 46029, 11, "either", BOTH, EITHER_UNIV),
    ("eng", 46894, 6, "either", BOTH, EITHER_UNIV),
    ("eng", 46895, 19, "either", BOTH, EITHER_UNIV),
    ("eng", 46934, 18, "either", BOTH, EITHER_UNIV),
    ("eng", 47428, 18, "either", BOTH, EITHER_UNIV),
    ("eng", 48644, 5, "either", BOTH, EITHER_UNIV),
    ("eng", 49106, 6, "either", BOTH, EITHER_UNIV),
    ("eng", 49158, 7, "either", BOTH, EITHER_UNIV),
    ("eng", 49335, 12, "either", BOTH, EITHER_UNIV),
    ("eng", 51218, 10, "either", BOTH, EITHER_UNIV),
    ("eng", 51365, 11, "either", BOTH, EITHER_UNIV),
    ("eng", 56131, 17, "either", BOTH, EITHER_UNIV),
    # elective either: ready to take up either side of a question
    ("eng", 47446, 10, "either", BOTH, EITHER_ELEC),
    # pronoun either: whoever might sell it to either of these
    ("eng", 13547, 13, "either", BOTH, EITHER_PRON),
    # either ... or: coordinator, tagged x like the other such tokens
    ("eng", 11341, 12, "either", BOTH, "x"),
    ("eng", 13318, 5, "either", BOTH, "x"),
    ("eng", 13564, 12, "either", BOTH, "x"),
    ("eng", 13937, 13, "either", BOTH, "x"),
    ("eng", 46034, 6, "either", BOTH, "x"),
    ("eng", 47449, 24, "either", BOTH, "x"),
    ("eng", 47603, 16, "either", BOTH, "x"),
    ("eng", 48154, 9, "either", BOTH, "x"),
    ("eng", 50875, 3, "either", BOTH, "x"),
    ("eng", 55903, 24, "either", BOTH, "x"),
    # 哪 'which': 走哪条路, 万一哪天, 哪位首相都, 有哪一位, 哪家餐厅, 有哪一例
    ("cmn", 244, 5, "哪", THAT, WHICH),
    ("cmn", 322, 5, "哪", THAT, WHICH),
    ("cmn", 10005, 9, "哪", THAT, WHICH),
    ("cmn", 10602, 2, "哪", THAT, WHICH),
    ("cmn", 61449, 0, "哪", THAT, WHICH),
    ("cmn", 100359, 4, "哪", THAT, WHICH),
]


def _is_synset(tag: str) -> bool:
    """Return True if a tag looks like a synset ID rather than a placeholder."""
    return "-" in tag


def retag(conn: sqlite3.Connection, lang: str, synsets: set[str],
          dry_run: bool) -> Counter:
    """Apply the RETAGS for one language.

    Args:
        conn: Connection to the language's corpus database.
        lang: Language code selecting rows of RETAGS.
        synsets: Synset IDs present in wn-ntumc.db.
        dry_run: If True, report changes without making them.

    Returns:
        Counts of 'retagged', 'already' and 'skipped' tokens.
    """
    counts: Counter = Counter()
    for lng, sid, cid, lemma, old, new in RETAGS:
        if lng != lang:
            continue
        row = conn.execute(
            "SELECT clemma, tag FROM concept WHERE sid = ? AND cid = ?",
            (sid, cid)).fetchone()
        if row is None or row[0] != lemma:
            logger.warning("%s %d/%d: no concept %r here, skipped",
                           lang, sid, cid, lemma)
            counts["skipped"] += 1
            continue
        tag = row[1]
        if tag == new:
            counts["already"] += 1
            continue
        if tag != old:
            logger.warning("%s %d/%d %s: tag is %r, not %r, skipped",
                           lang, sid, cid, lemma, tag, old)
            counts["skipped"] += 1
            continue
        if _is_synset(new) and new not in synsets:
            logger.warning("%s %d/%d: synset %s not in wordnet, skipped",
                           lang, sid, cid, new)
            counts["skipped"] += 1
            continue
        logger.info("%s %s %d/%d %s: %s -> %s",
                    "would retag" if dry_run else "retag",
                    lang, sid, cid, lemma, old, new)
        if not dry_run:
            conn.execute(
                "UPDATE concept SET tag = ? WHERE sid = ? AND cid = ?",
                (new, sid, cid))
        counts["retagged"] += 1
    return counts


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Retag either/哪 tokens after the pronoun fixes.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Report what would change, change nothing")
    group.add_argument("--fix", action="store_true",
                       help="Apply the retagging")
    args = parser.parse_args()

    wn = sqlite3.connect(str(BUILD / "wn-ntumc.db"))
    synsets = {r[0] for r in wn.execute("SELECT synset FROM synset")}
    wn.close()

    for lang in sorted({r[0] for r in RETAGS}):
        with sqlite3.connect(str(BUILD / f"{lang}.db")) as conn:
            counts = retag(conn, lang, synsets, args.dry_run)
        conn.close()
        logger.info("%s: %s %d, already done %d, skipped %d", lang,
                    "would retag" if args.dry_run else "retagged",
                    counts["retagged"], counts["already"], counts["skipped"])


if __name__ == "__main__":
    main()
