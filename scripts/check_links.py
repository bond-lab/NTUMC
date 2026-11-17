#!/usr/bin/env python3
"""Report, and with --fix delete, link rows whose ends no longer exist.

A link database (eng-jpn.db ...) holds sentence, word and concept links
between two corpus databases named in its meta table.  Sentences and
concepts get deleted or renumbered over the years, leaving link rows
that point at nothing; corpus_xml.py skips them when dumping, and this
script lists them so they can be repaired or removed.

Usage:
    .venv/bin/python scripts/check_links.py build/eng-jpn.db
    .venv/bin/python scripts/check_links.py build/eng-jpn.db --fix
    .venv/bin/python scripts/check_links.py build/*-*.db --build build

The corpus databases are looked for in the link database's directory
unless --build says otherwise.
"""

import argparse
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# link table -> (corpus table, key column of that table, id columns on each side)
LINK_TABLES = {
    "slink": ("sent", None, "slid"),
    "wlink": ("word", "wid", "wlid"),
    "clink": ("concept", "cid", "clid"),
}


@dataclass
class Dangling:
    """One link row with a missing end."""

    table: str
    key: int
    from_ids: tuple[int, ...]
    to_ids: tuple[int, ...]
    missing: str  # "from", "to" or "both"


def corpus_names(conn: sqlite3.Connection, link_db: Path) -> tuple[str, str]:
    """Return the (from, to) corpus database file names.

    They come from the meta table, or from the file name (eng-jpn.db ->
    eng.db, jpn.db) when the link database has no meta row.

    Args:
        conn: connection to the link database
        link_db: its path

    Returns:
        The two file names, e.g. ('eng.db', 'jpn.db')

    Raises:
        ValueError: if neither meta nor the file name gives two names
    """
    try:
        row = conn.execute("SELECT fcorpus, tcorpus FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    if row and row[0] and row[1]:
        return row[0], row[1]
    parts = link_db.stem.split("-")
    if len(parts) != 2:
        raise ValueError(f"{link_db}: no meta row and the name is not FROM-TO.db")
    logger.warning("%s: meta table empty, using the file name", link_db.name)
    return f"{parts[0]}.db", f"{parts[1]}.db"


def find_dangling(conn: sqlite3.Connection, table: str) -> list[Dangling]:
    """List the rows of one link table whose ends are missing.

    The corpus databases must be attached as `f` and `t`.

    Args:
        conn: connection to the link database
        table: 'slink', 'wlink' or 'clink'

    Returns:
        The dangling rows, in key order
    """
    corpus_table, sub, key = LINK_TABLES[table]
    f_ids = ["fsid"] + ([f"f{sub}"] if sub else [])
    t_ids = ["tsid"] + ([f"t{sub}"] if sub else [])
    join_f = "a.sid = l.fsid" + (f" AND a.{sub} = l.f{sub}" if sub else "")
    join_t = "b.sid = l.tsid" + (f" AND b.{sub} = l.t{sub}" if sub else "")
    cols = ", ".join([f"l.{key}"] + [f"l.{c}" for c in f_ids + t_ids])
    rows = conn.execute(
        f"SELECT {cols}, a.sid IS NULL, b.sid IS NULL FROM {table} l "
        f"LEFT JOIN f.{corpus_table} a ON {join_f} "
        f"LEFT JOIN t.{corpus_table} b ON {join_t} "
        f"WHERE a.sid IS NULL OR b.sid IS NULL ORDER BY l.{key}"
    ).fetchall()
    result = []
    n = len(f_ids)
    for row in rows:
        from_ids, to_ids = tuple(row[1 : 1 + n]), tuple(row[1 + n : 1 + 2 * n])
        missing = "both" if row[-2] and row[-1] else ("from" if row[-2] else "to")
        result.append(Dangling(table, row[0], from_ids, to_ids, missing))
    return result


def delete_dangling(conn: sqlite3.Connection, rows: list[Dangling]) -> int:
    """Delete the given link rows.

    Args:
        conn: connection to the link database (the caller commits)
        rows: rows from find_dangling

    Returns:
        Number of rows deleted
    """
    deleted = 0
    for row in rows:
        key = LINK_TABLES[row.table][2]
        deleted += conn.execute(
            f"DELETE FROM {row.table} WHERE {key} = ?", (row.key,)
        ).rowcount
    return deleted


def check(link_db: Path, build: Path | None, fix: bool) -> int:
    """Report the dangling rows of one link database, deleting them if fix.

    Args:
        link_db: the link database
        build: directory holding the corpus databases (default: link_db's)
        fix: delete the dangling rows

    Returns:
        Number of dangling rows found
    """
    conn = sqlite3.connect(str(link_db))
    f_name, t_name = corpus_names(conn, link_db)
    where = build or link_db.parent
    conn.execute("ATTACH ? AS f", (str(where / f_name),))
    conn.execute("ATTACH ? AS t", (str(where / t_name),))
    present = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    total = 0
    for table in LINK_TABLES:
        if table not in present:
            logger.warning("%s: no %s table", link_db.name, table)
            continue
        rows = find_dangling(conn, table)
        total += len(rows)
        for row in rows:
            logger.info(
                "%s %s %d: %s -> %s (%s side missing)",
                link_db.name,
                table,
                row.key,
                "/".join(map(str, row.from_ids)),
                "/".join(map(str, row.to_ids)),
                row.missing,
            )
        if rows and fix:
            with conn:
                deleted = delete_dangling(conn, rows)
            logger.info("%s: deleted %d %s rows", link_db.name, deleted, table)
    logger.info("%s: %d dangling link rows", link_db.name, total)
    conn.close()
    return total


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Report link rows whose sentence, word or concept is missing."
    )
    parser.add_argument("link_db", nargs="+", type=Path, help="link database(s)")
    parser.add_argument("--build", type=Path, help="directory of the corpus databases")
    parser.add_argument("--fix", action="store_true", help="delete the dangling rows")
    args = parser.parse_args()
    missing = [p for p in args.link_db if not p.exists()]
    if missing:
        logger.error("not found: %s", ", ".join(map(str, missing)))
        sys.exit(1)
    total = sum(check(p, args.build, args.fix) for p in args.link_db)
    sys.exit(1 if total and not args.fix else 0)


if __name__ == "__main__":
    main()
