#!/usr/bin/env python3
"""Migrate corpus databases: add genre column to the corpus table.

Adds ``genre TEXT NOT NULL CHECK (genre IN (...))`` to every corpus DB in
build/, populated from the existing ``corpus`` code.  Also drops any broken
triggers that reference log tables which no longer exist.

Run once after pulling this change::

    .venv/bin/python scripts/migrate_genre.py [--dry-run]

The migration is idempotent: DBs that already have a fully-populated genre
column with valid values are skipped.
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

# Canonical mapping from corpus code → genre.
# After migration, make_display.py queries the genre column directly;
# this dict is the single source of truth for the migration only.
CORPUS_CODE_TO_GENRE: dict[str, str] = {
    "kc":       "news",
    "story":    "fiction",
    "yoursing": "tourism",
    "essay":    "essay",
    "gloss":    "lexical",
    "comments": "online",
}

VALID_GENRES = sorted(set(CORPUS_CODE_TO_GENRE.values()))
_GENRE_IN = ", ".join(f"'{g}'" for g in VALID_GENRES)
_GENRE_CHECK = f"CHECK (genre IN ({_GENRE_IN}))"


def _drop_broken_triggers(conn: sqlite3.Connection, db_name: str) -> list[str]:
    """Drop triggers that reference missing tables or non-existent columns.

    Catches two common breakage patterns:
    - ``INSERT INTO <log_table>`` where ``<log_table>`` does not exist.
    - ``NEW.<col>`` / ``OLD.<col>`` where ``<col>`` is not on the trigger's table.

    Args:
        conn: Open database connection.
        db_name: DB filename for logging.

    Returns:
        Names of triggers that were dropped.
    """
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    table_cols: dict[str, set[str]] = {}
    dropped: list[str] = []

    for name, tbl_name, sql in conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall():
        if not sql:
            continue
        broken = False

        # Check 1: INSERT INTO a table that doesn't exist
        for target in re.findall(r"INSERT\s+INTO\s+(\w+)", sql, re.IGNORECASE):
            if target not in tables:
                broken = True
                break

        # Check 2: NEW.col / OLD.col issues
        if not broken and tbl_name in tables:
            if tbl_name not in table_cols:
                table_cols[tbl_name] = {
                    r[1]
                    for r in conn.execute(f"PRAGMA table_info({tbl_name})").fetchall()
                }
            event_m = re.search(r"\b(INSERT|UPDATE|DELETE)\b", sql, re.IGNORECASE)
            event = event_m.group(1).upper() if event_m else ""
            for prefix, col in re.findall(r"\b(NEW|OLD)\.(\w+)", sql, re.IGNORECASE):
                p = prefix.upper()
                # DELETE triggers have no NEW row; INSERT triggers have no OLD row
                if (event == "DELETE" and p == "NEW") or (event == "INSERT" and p == "OLD"):
                    broken = True
                    break
                if col not in table_cols[tbl_name]:
                    broken = True
                    break

        if broken:
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
            dropped.append(name)

    if dropped:
        conn.commit()
        print(
            f"  {db_name}: dropped {len(dropped)} broken trigger(s): "
            + ", ".join(dropped)
        )
    return dropped


def migrate_db(db_path: Path, dry_run: bool = False) -> bool:
    """Add genre column to corpus table in one database.

    Drops broken triggers first (triggers referencing non-existent log tables).
    Safe to re-run: fully migrated DBs are skipped.

    Args:
        db_path: Path to the SQLite corpus database.
        dry_run: If True, validate and report but do not write.

    Returns:
        True if migration was applied (or would be in dry-run).

    Raises:
        SystemExit: On unknown corpus code or DB error.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        # Drop broken triggers so schema changes can commit cleanly.
        if not dry_run:
            _drop_broken_triggers(conn, db_path.name)

        # Check current migration state.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(corpus)").fetchall()]
        if "genre" in cols:
            placeholders = ",".join("?" * len(VALID_GENRES))
            null_count = conn.execute(
                "SELECT COUNT(*) FROM corpus WHERE genre IS NULL"
            ).fetchone()[0]
            invalid_count = conn.execute(
                f"SELECT COUNT(*) FROM corpus WHERE genre NOT IN ({placeholders})",
                VALID_GENRES,
            ).fetchone()[0]
            if null_count == 0 and invalid_count == 0:
                print(f"  {db_path.name}: already migrated — skipping")
                return False
            print(
                f"  {db_path.name}: partial migration detected "
                f"(null={null_count}, invalid={invalid_count}), redoing"
            )

        # Validate all corpus codes before touching anything.
        rows = conn.execute(
            "SELECT corpusID, corpus, title, language FROM corpus ORDER BY corpusID"
        ).fetchall()
        unknown = [(cid, code) for cid, code, *_ in rows if code not in CORPUS_CODE_TO_GENRE]
        if unknown:
            for cid, code in unknown:
                print(
                    f"  ERROR {db_path.name}: unknown corpus code {code!r} "
                    f"(corpusID={cid}) — add it to CORPUS_CODE_TO_GENRE first"
                )
            sys.exit(1)

        if dry_run:
            for cid, code, *_ in rows:
                genre = CORPUS_CODE_TO_GENRE[code]
                print(f"  {db_path.name}: corpusID={cid} {code!r} → {genre!r}")
            return True

        # Recreate corpus table with genre column and CHECK constraint.
        # We copy all existing columns plus genre rather than relying on
        # ALTER TABLE, which can fail when broken triggers exist.
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS corpus_migration_new (
                corpusID INTEGER PRIMARY KEY,
                corpus   TEXT,
                title    TEXT,
                language TEXT,
                genre    TEXT NOT NULL {_GENRE_CHECK}
            )
        """)
        conn.execute("DELETE FROM corpus_migration_new")
        for cid, code, title, language in rows:
            genre = CORPUS_CODE_TO_GENRE[code]
            conn.execute(
                "INSERT INTO corpus_migration_new VALUES (?, ?, ?, ?, ?)",
                (cid, code, title, language, genre),
            )
        conn.execute("DROP TABLE IF EXISTS corpus")
        conn.execute("ALTER TABLE corpus_migration_new RENAME TO corpus")
        conn.commit()

        print(f"  {db_path.name}: migrated {len(rows)} corpus entries")
        return True

    except sqlite3.Error as exc:
        print(f"  ERROR {db_path.name}: {exc}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be migrated without writing",
    )
    parser.add_argument(
        "--build-dir", default=str(BUILD_DIR),
        help=f"Path to build directory (default: {BUILD_DIR})",
    )
    args = parser.parse_args()

    build_dir = Path(args.build_dir)
    dbs = sorted(
        p for p in build_dir.glob("*.db")
        if not p.stem.startswith("wn") and "-" not in p.stem
    )
    if not dbs:
        print(f"No corpus DBs found in {build_dir}")
        sys.exit(1)

    action = "Checking (dry run)" if args.dry_run else "Migrating"
    print(f"{action} {len(dbs)} corpus DB(s) in {build_dir}...")
    for db_path in dbs:
        migrate_db(db_path, dry_run=args.dry_run)
    print("Done.")


if __name__ == "__main__":
    main()
