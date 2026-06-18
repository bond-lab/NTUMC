#!/usr/bin/env python3
"""Populate missing cfrom/cto character offsets in the word table.

For each sentence, scans the sentence text left-to-right to find the
character position of each word (in wid order) and writes cfrom/cto
back to the database.

cfrom = start character index (inclusive)
cto   = end character index (exclusive, i.e. sent[cfrom:cto] == word)

Sentences where any word's cfrom/cto is already set are skipped by
default (use --overwrite to recalculate everything).

Usage:
    .venv/bin/python scripts/fix_cpos.py build/eng.db
    .venv/bin/python scripts/fix_cpos.py build/eng.db --docid 440
    .venv/bin/python scripts/fix_cpos.py build/eng.db --overwrite
    .venv/bin/python scripts/fix_cpos.py build/eng.db --dry-run
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def find_word_offsets(
    sent_text: str, words: list[str]
) -> list[tuple[int, int] | None]:
    """Locate each word in sent_text, scanning left-to-right.

    Returns a list of (cfrom, cto) tuples, or None where a word cannot
    be found (e.g. tokenisation mismatch).

    Args:
        sent_text: The full sentence string.
        words: Ordered list of surface word forms.

    Returns:
        List of (cfrom, cto) or None, same length as words.
    """
    results: list[tuple[int, int] | None] = []
    pos = 0
    for word in words:
        idx = sent_text.find(word, pos)
        if idx == -1:
            results.append(None)
            # Don't advance pos — try to recover on next word
        else:
            results.append((idx, idx + len(word)))
            pos = idx + len(word)
    return results


def process_db(
    db_path: str,
    docid: int | None = None,
    overwrite: bool = False,
    dry_run: bool = False,
    batch_size: int = 1000,
) -> None:
    """Fill cfrom/cto for all (or one) document(s) in the corpus DB.

    Args:
        db_path: Path to corpus SQLite database.
        docid: If given, process only this document; otherwise all docs.
        overwrite: If True, recalculate even where cfrom/cto already set.
        dry_run: If True, compute but do not write to DB.
        batch_size: Sentences per transaction.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    # The update trigger on word requires word_log; create it if absent
    conn.execute(
        """CREATE TABLE IF NOT EXISTS word_log (
            sid_new INTEGER, sid_old INTEGER,
            wid_new INTEGER, wid_old INTEGER,
            word_new TEXT,   word_old TEXT,
            pos_new TEXT,    pos_old TEXT,
            lemma_new TEXT,  lemma_old TEXT,
            cfrom_new INTEGER, cfrom_old INTEGER,
            cto_new INTEGER,   cto_old INTEGER,
            comment_new TEXT,  comment_old TEXT,
            usrname_new TEXT,  usrname_old TEXT,
            date_update TEXT
        )"""
    )
    conn.commit()

    # Build sentence query
    if docid is not None:
        where = "WHERE s.docID = ?"
        params: tuple = (docid,)
    else:
        where = ""
        params = ()

    skip_clause = "" if overwrite else "AND w_agg.has_cfrom = 0"

    # Pre-aggregate whether each sentence already has cfrom set
    sentences = conn.execute(
        f"""
        SELECT s.sid, s.sent
        FROM sent s
        JOIN (
            SELECT sid,
                   MAX(CASE WHEN cfrom IS NOT NULL THEN 1 ELSE 0 END) AS has_cfrom
            FROM word GROUP BY sid
        ) w_agg ON w_agg.sid = s.sid
        {where}
        {skip_clause}
        ORDER BY s.sid
        """,
        params,
    ).fetchall()

    total = len(sentences)
    if total == 0:
        logger.info("Nothing to update (all sentences already have cfrom/cto).")
        return
    logger.info(
        "%s%d sentence(s) to process%s.",
        "[DRY RUN] " if dry_run else "",
        total,
        " (overwrite mode)" if overwrite else "",
    )

    updated = skipped = failed = 0
    batch: list[tuple] = []

    def flush() -> None:
        nonlocal updated
        count = len(batch)
        if count:
            if not dry_run:
                conn.executemany(
                    "UPDATE word SET cfrom=?, cto=? WHERE sid=? AND wid=?",
                    batch,
                )
                conn.commit()
            updated += count
        batch.clear()

    for row in sentences:
        sid = row["sid"]
        sent_text = row["sent"] or ""

        words_rows = conn.execute(
            "SELECT wid, word FROM word WHERE sid=? ORDER BY wid", (sid,)
        ).fetchall()

        if not words_rows or not sent_text:
            skipped += 1
            continue

        wids    = [r["wid"] for r in words_rows]
        surfaces = [r["word"] for r in words_rows]

        offsets = find_word_offsets(sent_text, surfaces)

        any_ok = False
        for wid, offset in zip(wids, offsets):
            if offset is None:
                failed += 1
            else:
                cfrom, cto = offset
                batch.append((cfrom, cto, sid, wid))
                any_ok = True

        if not any_ok:
            skipped += 1

        if len(batch) >= batch_size:
            flush()

    flush()

    verb = "Would update" if dry_run else "Updated"
    logger.info(
        "%s %d word offsets (%d sentences skipped, %d mismatches).",
        verb, updated, skipped, failed,
    )

    conn.close()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Populate cfrom/cto character offsets in the word table."
    )
    parser.add_argument("db", help="Path to corpus SQLite database")
    parser.add_argument(
        "--docid", type=int, default=None, help="Process only this document ID"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recalculate even where cfrom/cto already set",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute offsets but do not write to DB",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if not Path(args.db).exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)

    process_db(
        db_path=args.db,
        docid=args.docid,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
