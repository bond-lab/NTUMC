#!/usr/bin/env python3
"""Fix cmn.db sid ranges so spec/danc match eng.db, and import kumo-no-ito.

Problem: During the 2015 merge, spec and danc ended up with swapped sid
ranges in cmn.db relative to eng.db/jpn.db:
  - spec: eng 10000-10598, cmn 11000-11619 (should be 10000-range)
  - danc: eng 11000-11607, cmn 10000-10605 (should be 11000-range)

This script:
  1. Swaps the sid ranges for spec and danc in cmn.db
  2. Imports kumo-no-ito (sids 11900-11965) from the old 2016 cmn.db

Usage:
    .venv/bin/python scripts/fix_cmn_sids.py --dry-run
    .venv/bin/python scripts/fix_cmn_sids.py --fix
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
CMN_DB = BUILD_DIR / "cmn.db"
OLD_CMN_DB = Path.home() / "work" / "ntu-mc" / "2016-11-30" / "cmn.db"

# Current (wrong) and target (correct) sid ranges
SPEC_CURRENT = (11000, 11619)  # spec currently in cmn.db
DANC_CURRENT = (10000, 10605)  # danc currently in cmn.db
TEMP_OFFSET = 90000            # temporary offset to avoid collisions during swap

# Bogus English sentence inserted by accident on the annotation server.
# It pushed all subsequent spec sids up by one, breaking alignment with
# the old 2016 annotations. Must be removed and the gap closed before
# the spec/danc swap.
BOGUS_SID = 11323              # "fields." — not a Chinese sentence

# Tables with a sid column that need updating
SID_TABLES = ["sent", "word", "concept", "cwl", "stype"]
# Tables with sid in a compound key or non-primary reference
SID_TABLES_OPTIONAL = ["sentiment", "xwl", "conceptV1", "chunks"]

KUMO_SID_RANGE = (11900, 11965)


def get_sid_tables(conn: sqlite3.Connection) -> list[str]:
    """Return tables that have a 'sid' column."""
    all_tables = {
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    result = []
    for table in SID_TABLES + SID_TABLES_OPTIONAL:
        if table not in all_tables:
            continue
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if "sid" in cols:
            result.append(table)
    return result


def count_rows(conn: sqlite3.Connection, table: str, sid_min: int, sid_max: int) -> int:
    """Count rows in a table within a sid range."""
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE sid BETWEEN ? AND ?",
        (sid_min, sid_max),
    ).fetchone()[0]


def remap_sids(
    conn: sqlite3.Connection,
    tables: list[str],
    old_min: int, old_max: int,
    new_min: int,
    dry_run: bool,
) -> int:
    """Remap sids from [old_min, old_max] by shifting to start at new_min.

    Args:
        conn: Database connection.
        tables: Tables to update.
        old_min: Current minimum sid.
        old_max: Current maximum sid.
        new_min: Target minimum sid.
        dry_run: If True, only report.

    Returns:
        Total rows affected.
    """
    delta = new_min - old_min
    if delta == 0:
        return 0
    total = 0
    for table in tables:
        n = count_rows(conn, table, old_min, old_max)
        if n == 0:
            continue
        total += n
        if dry_run:
            logger.info(
                "  %s: would shift %d rows by %+d (sid %d-%d → %d-%d)",
                table, n, delta, old_min, old_max,
                old_min + delta, old_max + delta,
            )
        else:
            conn.execute(
                f"UPDATE {table} SET sid = sid + ? WHERE sid BETWEEN ? AND ?",
                (delta, old_min, old_max),
            )
    return total


def delete_bogus_sentence(
    conn: sqlite3.Connection, tables: list[str], dry_run: bool,
) -> None:
    """Delete the bogus 'fields.' sentence and close the sid gap.

    The annotation server has an accidental English sentence "fields."
    at sid 11323 in the spec range.  This shifted all subsequent sids
    by +1 relative to the 2016 annotations.  Deleting it and shifting
    sids 11324+ down by 1 restores the original alignment.
    """
    sent = conn.execute(
        "SELECT sent FROM sent WHERE sid = ?", (BOGUS_SID,)
    ).fetchone()
    if not sent:
        logger.info("Bogus sid %d not found (already removed?), skipping", BOGUS_SID)
        return
    if sent[0].strip() != "fields.":
        logger.info(
            "sid %d is not 'fields.' (got %r), skipping",
            BOGUS_SID, sent[0][:40],
        )
        return

    spec_max = SPEC_CURRENT[1]
    logger.info(
        "Deleting bogus sentence at sid %d ('fields.') and closing gap",
        BOGUS_SID,
    )

    if not dry_run:
        for table in tables:
            conn.execute(
                f"DELETE FROM {table} WHERE sid = ?", (BOGUS_SID,)
            )
        for table in tables:
            n = count_rows(conn, table, BOGUS_SID + 1, spec_max)
            if n == 0:
                continue
            for sid in range(BOGUS_SID + 1, spec_max + 1):
                conn.execute(
                    f"UPDATE {table} SET sid = ? WHERE sid = ?",
                    (sid - 1, sid),
                )
        conn.commit()

        new_max = conn.execute(
            "SELECT MAX(sid) FROM sent WHERE docID="
            "(SELECT docid FROM doc WHERE doc='spec')"
        ).fetchone()[0]
        logger.info("  spec max sid now %d (was %d)", new_max, spec_max)


def swap_spec_danc(conn: sqlite3.Connection, tables: list[str], dry_run: bool) -> None:
    """Swap spec and danc sid ranges using a temporary offset."""
    spec_range = conn.execute(
        "SELECT MIN(sid), MAX(sid) FROM sent WHERE docID="
        "(SELECT docid FROM doc WHERE doc='spec')"
    ).fetchone()
    danc_range = conn.execute(
        "SELECT MIN(sid), MAX(sid) FROM sent WHERE docID="
        "(SELECT docid FROM doc WHERE doc='danc')"
    ).fetchone()
    spec_min, spec_max = spec_range
    danc_min, danc_max = danc_range

    logger.info("Step 1: Move spec (%d-%d) to temp (%d+)", spec_min, spec_max, TEMP_OFFSET)
    remap_sids(conn, tables, spec_min, spec_max, TEMP_OFFSET, dry_run)

    logger.info("Step 2: Move danc (%d-%d) to spec range (%d+)", danc_min, danc_max, spec_min)
    remap_sids(conn, tables, danc_min, danc_max, spec_min, dry_run)

    # danc's new location is where spec was: 11000+
    # danc had sids 10000-10605 → need to go to 11000-11605
    danc_new_min = spec_min  # 11000

    logger.info("Step 3: Move spec from temp (%d+) to danc range (%d+)", TEMP_OFFSET, danc_min)
    temp_max = TEMP_OFFSET + (spec_max - spec_min)
    remap_sids(conn, tables, TEMP_OFFSET, temp_max, danc_min, dry_run)

    if not dry_run:
        conn.commit()
        # Verify
        new_spec = conn.execute(
            "SELECT MIN(sid), MAX(sid) FROM sent WHERE docID="
            "(SELECT docid FROM doc WHERE doc='spec')"
        ).fetchone()
        new_danc = conn.execute(
            "SELECT MIN(sid), MAX(sid) FROM sent WHERE docID="
            "(SELECT docid FROM doc WHERE doc='danc')"
        ).fetchone()
        logger.info("Verified: spec now %s, danc now %s", new_spec, new_danc)


def import_kumo(conn: sqlite3.Connection, old_db: Path, dry_run: bool) -> None:
    """Import kumo-no-ito data from the old cmn.db."""
    if not old_db.exists():
        logger.error("Old cmn.db not found: %s", old_db)
        return

    old_conn = sqlite3.connect(str(old_db))
    kumo_min, kumo_max = KUMO_SID_RANGE

    # Check if kumo-no-ito already exists
    existing = conn.execute(
        "SELECT COUNT(*) FROM sent WHERE sid BETWEEN ? AND ?",
        (kumo_min, kumo_max),
    ).fetchone()[0]
    if existing > 0:
        logger.info("kumo-no-ito sids %d-%d already have %d rows, skipping", kumo_min, kumo_max, existing)
        old_conn.close()
        return

    # Check if doc entry exists
    doc_row = conn.execute("SELECT docid FROM doc WHERE doc='kumo-no-ito'").fetchone()
    if doc_row:
        docid = doc_row[0]
        logger.info("kumo-no-ito doc entry exists (docid=%d)", docid)
    else:
        old_doc = old_conn.execute(
            "SELECT docid, doc, title, subtitle, corpusID FROM doc WHERE doc='kumo-no-ito'"
        ).fetchone()
        if not old_doc:
            logger.error("kumo-no-ito not found in old cmn.db")
            old_conn.close()
            return
        docid = old_doc[0]
        logger.info("Will create doc entry: docid=%d, title='%s'", docid, old_doc[2])
        if not dry_run:
            conn.execute(
                "INSERT INTO doc (docid, doc, title, subtitle, corpusID) VALUES (?, ?, ?, ?, ?)",
                old_doc,
            )

    # Import each table
    for table in ["sent", "word", "concept", "cwl", "stype"]:
        old_tables = {
            r[0] for r in old_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if table not in old_tables:
            continue

        cols_info = old_conn.execute(f"PRAGMA table_info({table})").fetchall()
        col_names = [r[1] for r in cols_info]

        # Match columns to current DB
        cur_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        shared_cols = [c for c in col_names if c in cur_cols]

        col_str = ", ".join(shared_cols)
        rows = old_conn.execute(
            f"SELECT {col_str} FROM {table} WHERE sid BETWEEN ? AND ?",
            (kumo_min, kumo_max),
        ).fetchall()

        if not rows:
            continue

        ph = ", ".join("?" * len(shared_cols))
        logger.info(
            "  %s: %s %d rows (cols: %s)",
            table, "would import" if dry_run else "importing",
            len(rows), col_str,
        )
        if not dry_run:
            conn.executemany(
                f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({ph})",
                rows,
            )

    # Import sentiment if it exists in both
    for table in ["sentiment"]:
        old_tables = {
            r[0] for r in old_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        cur_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if table in old_tables and table in cur_tables:
            cols_info = old_conn.execute(f"PRAGMA table_info({table})").fetchall()
            col_names = [r[1] for r in cols_info]
            cur_cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            shared_cols = [c for c in col_names if c in cur_cols]
            col_str = ", ".join(shared_cols)
            rows = old_conn.execute(
                f"SELECT {col_str} FROM {table} WHERE sid BETWEEN ? AND ?",
                (kumo_min, kumo_max),
            ).fetchall()
            if rows:
                ph = ", ".join("?" * len(shared_cols))
                logger.info("  %s: %s %d rows", table, "would import" if dry_run else "importing", len(rows))
                if not dry_run:
                    conn.executemany(
                        f"INSERT OR IGNORE INTO {table} ({col_str}) VALUES ({ph})",
                        rows,
                    )

    if not dry_run:
        conn.commit()
        n = conn.execute(
            "SELECT COUNT(*) FROM sent WHERE sid BETWEEN ? AND ?",
            (kumo_min, kumo_max),
        ).fetchone()[0]
        logger.info("Verified: %d kumo-no-ito sentences imported", n)

    old_conn.close()


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Fix cmn.db sid ranges for spec/danc and import kumo-no-ito."
    )
    parser.add_argument("--fix", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    if not CMN_DB.exists():
        logger.error("cmn.db not found: %s", CMN_DB)
        sys.exit(1)

    conn = sqlite3.connect(str(CMN_DB))
    conn.execute("PRAGMA foreign_keys = OFF")

    # Disable triggers during bulk update to avoid log table errors
    triggers = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    if triggers and not args.dry_run:
        logger.info("Temporarily dropping %d triggers...", len(triggers))
        for name, _ in triggers:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        conn.commit()

    tables = get_sid_tables(conn)
    logger.info("Tables with sid column: %s", tables)

    # Show current state
    for doc in ["spec", "danc"]:
        r = conn.execute(
            "SELECT MIN(sid), MAX(sid), COUNT(*) FROM sent WHERE docID="
            f"(SELECT docid FROM doc WHERE doc='{doc}')"
        ).fetchone()
        logger.info("Current %s: sids %s-%s (%s sents)", doc, r[0], r[1], r[2])

    logger.info("")
    logger.info("=== Removing bogus 'fields.' sentence ===")
    delete_bogus_sentence(conn, tables, dry_run=args.dry_run)

    logger.info("")
    logger.info("=== Swapping spec and danc sid ranges ===")
    swap_spec_danc(conn, tables, dry_run=args.dry_run)

    logger.info("")
    logger.info("=== Importing kumo-no-ito from %s ===", OLD_CMN_DB)
    import_kumo(conn, OLD_CMN_DB, dry_run=args.dry_run)

    # Restore triggers
    if triggers and not args.dry_run:
        logger.info("Restoring %d triggers...", len(triggers))
        for _, sql in triggers:
            if sql:
                conn.execute(sql)
        conn.commit()

    conn.close()
    logger.info("Done.")


if __name__ == "__main__":
    main()
