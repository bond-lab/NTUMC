#!/usr/bin/env python3
"""Restore the change-log triggers in corpus databases.

The 2026-08-10 push left the server's eng.db with no triggers (all 14
lost) and cmn.db without delete_concept_log and delete_cwl_log, so
annotation edits there were no longer logged.  cmn.db's
delete_word_log also wrote to sent_log, so deleting a word failed.

For each database this creates every trigger in corpus_triggers.sql
(taken from the 2025-02 eng.db, where all are valid) that is missing,
and replaces any trigger on a table that writes to the wrong log table.
Existing correct triggers are left alone.  Idempotent.

Usage:
    .venv/bin/python scripts/2026-07/restore_triggers.py build/eng.db build/cmn.db --dry-run
    .venv/bin/python scripts/2026-07/restore_triggers.py build/eng.db build/cmn.db --fix
"""

import argparse
import logging
import re
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TRIGGERS_SQL = Path(__file__).with_name("corpus_triggers.sql")
NAME = re.compile(r"CREATE\s+TRIGGER\s+(\w+)\s+AFTER\s+\w+\s+ON\s+(\w+)", re.IGNORECASE)
TARGET = re.compile(r"INSERT\s+INTO\s+(\w+)", re.IGNORECASE)


def load_triggers(path: Path = TRIGGERS_SQL) -> dict[str, str]:
    """Return {trigger name: CREATE TRIGGER statement} from the SQL file."""
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.startswith("--"))
    # trigger bodies contain ';', so split after each closing END;
    stmts = [s.strip() for s in re.split(r"(?<=\bEND;)", text) if s.strip()]
    return {NAME.search(s).group(1): s for s in stmts}


def misdirected(sql: str) -> bool:
    """True if a trigger on table T writes somewhere other than T_log."""
    m, t = NAME.search(sql), TARGET.search(sql)
    return bool(m and t and t.group(1) != m.group(2) + "_log")


def restore(conn: sqlite3.Connection, canonical: dict[str, str],
            dry_run: bool) -> list[str]:
    """Create missing triggers and replace misdirected ones.

    Args:
        conn: Connection to a corpus database.
        canonical: Trigger statements by name.
        dry_run: If True, report without changing anything.

    Returns:
        Descriptions of the changes made (or that would be made).
    """
    have = dict(conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"))
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    changes = []
    for name, sql in canonical.items():
        on_table = NAME.search(sql).group(2)
        if on_table not in tables:
            continue
        if name not in have:
            changes.append(f"create {name}")
        elif misdirected(have[name]):
            changes.append(f"replace {name} (wrote to "
                           f"{TARGET.search(have[name]).group(1)})")
            if not dry_run:
                conn.execute(f"DROP TRIGGER [{name}]")
        else:
            continue
        if not dry_run:
            conn.execute(sql)
    if not dry_run:
        conn.commit()
    return changes


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("dbs", nargs="+", help="Corpus databases to repair")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Report what would change, change nothing")
    group.add_argument("--fix", action="store_true", help="Restore triggers")
    args = parser.parse_args()

    canonical = load_triggers()
    for db in args.dbs:
        conn = sqlite3.connect(db)
        changes = restore(conn, canonical, args.dry_run)
        n = conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger'").fetchone()[0]
        conn.close()
        logger.info("%s: %s; %d triggers now", db,
                    ", ".join(changes) if changes else "nothing to do", n)


if __name__ == "__main__":
    main()
