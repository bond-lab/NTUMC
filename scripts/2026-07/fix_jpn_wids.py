#!/usr/bin/env python3
"""Normalize Japanese word and concept IDs to be 0-based per sentence.

Some documents (kc01, kc02, catb, danc) use document-global numbering
instead of per-sentence 0-based numbering.  This script renumbers both
wids and cids to start at 0 for each sentence, updating all referencing
tables (word, cwl, concept) and cross-lingual clinks in eng-jpn.db.

Usage:
    .venv/bin/python scripts/fix_jpn_wids.py --dry-run
    .venv/bin/python scripts/fix_jpn_wids.py --fix
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
JPN_DB = BUILD_DIR / "jpn.db"
LINK_DB = BUILD_DIR / "eng-jpn.db"


def find_wids_to_fix(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """Find sentences whose wids don't start at 0.

    Returns:
        {sid: [old_wids sorted]}.
    """
    rows = conn.execute("""
        SELECT sid, MIN(wid) as minw
        FROM word GROUP BY sid
        HAVING minw != 0
    """).fetchall()

    result = {}
    for sid, _ in rows:
        wids = [r[0] for r in conn.execute(
            "SELECT wid FROM word WHERE sid = ? ORDER BY wid", (sid,),
        ).fetchall()]
        result[sid] = wids

    return result


def find_cids_to_fix(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """Find sentences whose cids don't start at 0.

    Returns:
        {sid: [old_cids sorted]}.
    """
    rows = conn.execute("""
        SELECT sid, MIN(cid) as minc
        FROM concept GROUP BY sid
        HAVING minc != 0
    """).fetchall()

    result = {}
    for sid, _ in rows:
        cids = [r[0] for r in conn.execute(
            "SELECT cid FROM concept WHERE sid = ? ORDER BY cid", (sid,),
        ).fetchall()]
        result[sid] = cids

    return result


def disable_triggers(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """Drop triggers and return them for later restoration."""
    triggers = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    for name, _ in triggers:
        conn.execute(f"DROP TRIGGER [{name}]")
    return triggers


def restore_triggers(
    conn: sqlite3.Connection, triggers: list[tuple[str, str]],
) -> None:
    """Restore previously dropped triggers."""
    for _, sql in triggers:
        if sql:
            conn.executescript(sql)


def fix_wids(
    conn: sqlite3.Connection,
    to_fix: dict[int, list[int]],
) -> tuple[int, int]:
    """Renumber wids to 0-based, updating word and cwl.

    Returns:
        (word_rows_updated, cwl_rows_updated).
    """
    total_words = 0
    total_cwl = 0
    for sid, old_wids in to_fix.items():
        for new_wid, old_wid in enumerate(old_wids):
            if old_wid == new_wid:
                continue
            conn.execute(
                "UPDATE word SET wid = ? WHERE sid = ? AND wid = ?",
                (new_wid, sid, old_wid),
            )
            total_words += 1
            total_cwl += conn.execute(
                "UPDATE cwl SET wid = ? WHERE sid = ? AND wid = ?",
                (new_wid, sid, old_wid),
            ).rowcount

    return total_words, total_cwl


def fix_cids(
    conn: sqlite3.Connection,
    to_fix: dict[int, list[int]],
    link_conn: sqlite3.Connection | None,
) -> tuple[int, int, int]:
    """Renumber cids to 0-based, updating concept, cwl, and clinks.

    Returns:
        (concept_rows, cwl_rows, clink_rows) updated.
    """
    total_concept = 0
    total_cwl = 0
    total_clink = 0

    for sid, old_cids in to_fix.items():
        for new_cid, old_cid in enumerate(old_cids):
            if old_cid == new_cid:
                continue
            conn.execute(
                "UPDATE concept SET cid = ? WHERE sid = ? AND cid = ?",
                (new_cid, sid, old_cid),
            )
            total_concept += 1
            total_cwl += conn.execute(
                "UPDATE cwl SET cid = ? WHERE sid = ? AND cid = ?",
                (new_cid, sid, old_cid),
            ).rowcount

            if link_conn:
                total_clink += link_conn.execute(
                    "UPDATE clink SET tcid = ? WHERE tsid = ? AND tcid = ?",
                    (new_cid, sid, old_cid),
                ).rowcount

    return total_concept, total_cwl, total_clink


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Normalize Japanese word/concept IDs to 0-based per sentence."
    )
    parser.add_argument("--fix", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    if not JPN_DB.exists():
        logger.error("jpn.db not found: %s", JPN_DB)
        sys.exit(1)

    conn = sqlite3.connect(str(JPN_DB))

    wids_to_fix = find_wids_to_fix(conn)
    cids_to_fix = find_cids_to_fix(conn)

    if not wids_to_fix and not cids_to_fix:
        logger.info("All wids and cids already 0-based, nothing to do")
        conn.close()
        return

    if wids_to_fix:
        logger.info(
            "%d sentences need wid renumbering (min_wid range: %d-%d)",
            len(wids_to_fix),
            min(wids[0] for wids in wids_to_fix.values()),
            max(wids[0] for wids in wids_to_fix.values()),
        )
    if cids_to_fix:
        logger.info(
            "%d sentences need cid renumbering (min_cid range: %d-%d)",
            len(cids_to_fix),
            min(cids[0] for cids in cids_to_fix.values()),
            max(cids[0] for cids in cids_to_fix.values()),
        )

    if args.dry_run:
        logger.info("Would fix %d wid + %d cid sentences",
                     len(wids_to_fix), len(cids_to_fix))
        conn.close()
        return

    link_conn = None
    if LINK_DB.exists() and cids_to_fix:
        link_conn = sqlite3.connect(str(LINK_DB))

    triggers = disable_triggers(conn)

    if wids_to_fix:
        ww, wc = fix_wids(conn, wids_to_fix)
        logger.info("  wids: updated %d word + %d cwl rows", ww, wc)

    if cids_to_fix:
        cc, ccwl, cl = fix_cids(conn, cids_to_fix, link_conn)
        logger.info("  cids: updated %d concept + %d cwl + %d clink rows",
                     cc, ccwl, cl)

    restore_triggers(conn, triggers)
    conn.commit()

    if link_conn:
        link_conn.commit()
        link_conn.close()

    remaining_wid = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT sid, MIN(wid) as minw FROM word GROUP BY sid HAVING minw != 0
        )
    """).fetchone()[0]
    remaining_cid = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT sid, MIN(cid) as minc FROM concept GROUP BY sid HAVING minc != 0
        )
    """).fetchone()[0]
    logger.info("Remaining: %d non-0 wid, %d non-0 cid", remaining_wid, remaining_cid)

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
