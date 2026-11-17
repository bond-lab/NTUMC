#!/usr/bin/env python3
"""Renumber English concept ids to 0-based per sentence.

The 2013 essay database numbered concepts across the whole document, and
merge_old_corpora.py kept those ids when it added *The Cathedral and the
Bazaar* (catb) to eng.db: sentence 26 holds cids 250-259, sentence 700
cids 10000 and up.  Every other English document, the Japanese and
Chinese copies of the essay (fix_jpn_wids.py) and the cross-lingual
links that realign_clinks.py derives count from 0 in each sentence, so
about half of the concept links into English (5,992 in eng-jpn.db,
4,799 in eng-cmn.db) pointed at concept ids that do not exist, and a
few in the first sentences pointed at the wrong concept.

This script renumbers the concepts of every sentence whose lowest cid is
not 0 to 0, 1, 2 ... in cid order, in concept, cwl and sentiment.  Three
other sentences qualify (a deleted concept 0 in houn 47898, danc 11115
and yoursing 102169); the links into 102169 already use the 0-based
positions, so they come right too.  The link databases are not changed:
pass them with --link to see how many of their links resolve before and
after.  The change-log triggers stay active, so every update is logged.

Usage:
    .venv/bin/python scripts/2026-07/fix_eng_cids.py --dry-run \\
        --link build/eng-jpn.db build/eng-cmn.db build/eng-ind.db
    .venv/bin/python scripts/2026-07/fix_eng_cids.py --fix \\
        --link build/eng-jpn.db build/eng-cmn.db build/eng-ind.db
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD = Path(__file__).resolve().parents[2] / "build"
ENG_DB = BUILD / "eng.db"

# Tables keyed by (sid, cid) that must follow the renumbering.
CID_TABLES = ("concept", "cwl", "sentiment")


def find_cids_to_fix(conn: sqlite3.Connection) -> dict[int, list[int]]:
    """Return {sid: [cids in order]} for sentences whose lowest cid is not 0."""
    rows = conn.execute(
        "SELECT sid, cid FROM concept WHERE sid IN "
        "(SELECT sid FROM concept GROUP BY sid HAVING MIN(cid) != 0) "
        "ORDER BY sid, cid"
    ).fetchall()
    result: dict[int, list[int]] = {}
    for sid, cid in rows:
        result.setdefault(sid, []).append(cid)
    return result


def renumber(conn: sqlite3.Connection, to_fix: dict[int, list[int]]) -> dict[str, int]:
    """Renumber the given sentences' cids to 0-based in every (sid, cid) table.

    Updates run in ascending cid order: the i-th cid is at least i, and
    every smaller cid has already moved to a smaller position, so no
    update can collide with an existing primary key.

    Args:
        conn: open corpus database connection (the caller commits)
        to_fix: {sid: [cids in order]} as returned by find_cids_to_fix

    Returns:
        {table: rows updated}.
    """
    counts = dict.fromkeys(CID_TABLES, 0)
    for sid, old_cids in to_fix.items():
        for new_cid, old_cid in enumerate(old_cids):
            if old_cid == new_cid:
                continue
            for table in CID_TABLES:
                counts[table] += conn.execute(
                    f"UPDATE {table} SET cid = ? WHERE sid = ? AND cid = ?",
                    (new_cid, sid, old_cid),
                ).rowcount
    return counts


def link_resolution(link_db: Path, eng_db: Path) -> tuple[int, int]:
    """Count the clinks in link_db whose English end exists in eng_db.

    The English side is `fsid`/`fcid` when the link database is named
    eng-XXX.db, `tsid`/`tcid` when it is XXX-eng.db (the meta table is
    empty in some link databases, so the file name decides).

    Args:
        link_db: the link database
        eng_db: the English corpus database

    Returns:
        (resolved, total).
    """
    conn = sqlite3.connect(str(link_db))
    conn.execute("ATTACH ? AS e", (str(eng_db),))
    side = "f" if link_db.stem.split("-")[0] == eng_db.stem else "t"
    resolved, total = conn.execute(
        f"SELECT SUM(c.sid IS NOT NULL), COUNT(*) FROM clink l "
        f"LEFT JOIN e.concept c ON c.sid = l.{side}sid AND c.cid = l.{side}cid"
    ).fetchone()
    conn.close()
    return resolved or 0, total


def report_links(links: list[Path], eng_db: Path, when: str) -> None:
    """Log how many clinks in each link database resolve against eng_db."""
    for link_db in links:
        resolved, total = link_resolution(link_db, eng_db)
        logger.info(
            "%s: %s %d of %d clinks resolve", when, link_db.name, resolved, total
        )


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Renumber English concept ids to 0-based per sentence."
    )
    parser.add_argument(
        "db",
        nargs="?",
        type=Path,
        default=ENG_DB,
        help="corpus database (default build/eng.db)",
    )
    parser.add_argument(
        "--link",
        nargs="*",
        type=Path,
        default=[],
        help="link databases to report resolution for",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--fix", action="store_true", help="apply changes")
    group.add_argument("--dry-run", action="store_true", help="report only")
    args = parser.parse_args()

    if not args.db.exists():
        logger.error("database not found: %s", args.db)
        sys.exit(1)

    conn = sqlite3.connect(str(args.db))
    to_fix = find_cids_to_fix(conn)
    if not to_fix:
        logger.info("all cids already 0-based, nothing to do")
        conn.close()
        return
    logger.info(
        "%d sentences need cid renumbering (%d concepts; lowest cid %d-%d)",
        len(to_fix),
        sum(len(c) for c in to_fix.values()),
        min(c[0] for c in to_fix.values()),
        max(c[0] for c in to_fix.values()),
    )
    report_links(args.link, args.db, "before")

    if args.dry_run:
        conn.close()
        return

    with conn:
        counts = renumber(conn, to_fix)
    conn.close()
    logger.info("updated %s", ", ".join(f"{t} {n}" for t, n in counts.items()))
    report_links(args.link, args.db, "after")


if __name__ == "__main__":
    main()
