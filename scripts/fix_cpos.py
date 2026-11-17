#!/usr/bin/env python3
"""Populate or repair cfrom/cto character offsets in the word table.

For each sentence, scans the sentence text left-to-right to find the
character position of each word (in wid order) and writes cfrom/cto
back to the database.

cfrom = start character index (inclusive)
cto   = end character index (exclusive, i.e. sent[cfrom:cto] == word)

By default only sentences with no offsets at all are filled in (an
empty string counts as no offset).  --overwrite recalculates every
sentence.  --mismatched repairs just the sentences whose stored offsets
do not match the text (drifted after an edit, or imported wrongly): it
is strict, so a sentence is only rewritten when every word is found in
order with at most --max-gap characters between words, and only the
words whose offsets change are written.

Usage:
    .venv/bin/python scripts/fix_cpos.py build/eng.db
    .venv/bin/python scripts/fix_cpos.py build/eng.db --docid 440
    .venv/bin/python scripts/fix_cpos.py build/eng.db --overwrite
    .venv/bin/python scripts/fix_cpos.py build/eng.db --mismatched --dry-run
"""

import argparse
import logging
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

Offset = tuple[int, int] | None


@dataclass
class Options:
    """What to process and how."""

    docid: int | None = None
    overwrite: bool = False
    mismatched: bool = False
    max_gap: int | None = None
    dry_run: bool = False
    batch_size: int = 1000


@dataclass
class Counts:
    """Outcome of a run."""

    sentences: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def find_word_offsets(
    sent_text: str, words: list[str], max_gap: int | None = None
) -> list[Offset]:
    """Locate each word in sent_text, scanning left-to-right.

    Args:
        sent_text: The full sentence string.
        words: Ordered list of surface word forms.
        max_gap: If given, a word found more than this many characters
            after the end of the previous word counts as not found.

    Returns:
        List of (cfrom, cto) or None (word not found), same length as words.
    """
    results: list[Offset] = []
    pos = 0
    for word in words:
        idx = sent_text.find(word, pos)
        if idx == -1 or (max_gap is not None and idx - pos > max_gap):
            results.append(None)
            # Don't advance pos: try to recover on the next word
        else:
            results.append((idx, idx + len(word)))
            pos = idx + len(word)
    return results


def select_sentences(conn: sqlite3.Connection, opts: Options) -> list[tuple[int, str]]:
    """Return the (sid, text) of the sentences to process.

    Args:
        conn: corpus database connection
        opts: docid restricts to one document; mismatched selects the
            sentences with a stored offset that does not match the text;
            overwrite selects all; otherwise only sentences without offsets

    Returns:
        Sentences in sid order
    """
    where = "WHERE s.docID = ?" if opts.docid is not None else "WHERE 1"
    params: tuple = (opts.docid,) if opts.docid is not None else ()
    if opts.mismatched:
        sql = f"""
            SELECT DISTINCT s.sid, s.sent FROM sent s
            JOIN word w ON w.sid = s.sid
            {where}
              AND w.cfrom IS NOT NULL AND w.cfrom != ''
              AND w.cto IS NOT NULL AND w.cto != ''
              AND substr(s.sent, w.cfrom + 1, w.cto - w.cfrom) != w.word
            ORDER BY s.sid"""
    else:
        has = "" if opts.overwrite else "AND w_agg.has_cfrom = 0"
        sql = f"""
            SELECT s.sid, s.sent FROM sent s
            JOIN (SELECT sid,
                         MAX(cfrom IS NOT NULL AND cfrom != '') AS has_cfrom
                  FROM word GROUP BY sid) w_agg ON w_agg.sid = s.sid
            {where} {has}
            ORDER BY s.sid"""
    return conn.execute(sql, params).fetchall()


def sentence_updates(
    sent_text: str, words: list[tuple[int, str, object, object]], opts: Options
) -> tuple[list[tuple[int, int, int]], int]:
    """Compute the (cfrom, cto, wid) rows to write for one sentence.

    Args:
        sent_text: the sentence text
        words: (wid, word, cfrom, cto) in wid order
        opts: mismatched makes the match strict: when a word is not
            found the whole sentence is left alone

    Returns:
        The rows whose offsets change, and the number of words not found
    """
    offsets = find_word_offsets(sent_text, [w[1] for w in words], opts.max_gap)
    not_found = offsets.count(None)
    if opts.mismatched and not_found:
        return [], not_found
    rows = [
        (off[0], off[1], wid)
        for (wid, _, cfrom, cto), off in zip(words, offsets)
        if off is not None and (cfrom, cto) != off
    ]
    return rows, not_found


def process_db(db_path: str, opts: Options) -> Counts:
    """Fill or repair cfrom/cto for the selected sentences of a corpus DB.

    Args:
        db_path: Path to corpus SQLite database.
        opts: What to process; dry_run computes but does not write.

    Returns:
        Counts of sentences processed, words updated, sentences skipped
        and words (or, with mismatched, sentences) that could not be placed.
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")

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

    sentences = select_sentences(conn, opts)
    counts = Counts(sentences=len(sentences))
    if not sentences:
        logger.info("Nothing to update.")
        return counts
    logger.info(
        "%s%d sentence(s) to process%s.",
        "[DRY RUN] " if opts.dry_run else "",
        len(sentences),
        " (overwrite mode)" if opts.overwrite else "",
    )

    batch: list[tuple[int, int, int, int]] = []

    def flush() -> None:
        if batch and not opts.dry_run:
            with conn:
                conn.executemany(
                    "UPDATE word SET cfrom = ?, cto = ? WHERE sid = ? AND wid = ?",
                    batch,
                )
        counts.updated += len(batch)
        batch.clear()

    for sid, sent_text in sentences:
        words = conn.execute(
            "SELECT wid, word, cfrom, cto FROM word WHERE sid = ? ORDER BY wid",
            (sid,),
        ).fetchall()
        if not words or not sent_text:
            counts.skipped += 1
            continue
        updates, not_found = sentence_updates(sent_text, words, opts)
        if opts.mismatched and not_found:
            counts.failed += 1
            logger.debug("sentence %d: a word was not found in the text", sid)
            continue
        counts.failed += not_found
        batch.extend((cfrom, cto, sid, wid) for cfrom, cto, wid in updates)
        if len(batch) >= opts.batch_size:
            flush()
    flush()

    logger.info(
        "%s %d word offsets (%d sentences skipped, %d %s).",
        "Would update" if opts.dry_run else "Updated",
        counts.updated,
        counts.skipped,
        counts.failed,
        "sentences not matched" if opts.mismatched else "words not found",
    )
    conn.close()
    return counts


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Populate or repair cfrom/cto character offsets in the word table."
    )
    parser.add_argument("db", help="Path to corpus SQLite database")
    parser.add_argument("--docid", type=int, help="Process only this document ID")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Recalculate even where cfrom/cto already set",
    )
    parser.add_argument(
        "--mismatched",
        action="store_true",
        help="Repair only sentences whose stored offsets do not match the text",
    )
    parser.add_argument(
        "--max-gap",
        type=int,
        help="Most characters allowed between consecutive words "
        "(default 3 with --mismatched, unlimited otherwise)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Compute offsets but do not write"
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    if not Path(args.db).exists():
        logger.error("Database not found: %s", args.db)
        sys.exit(1)
    max_gap = args.max_gap
    if max_gap is None and args.mismatched:
        max_gap = 3
    process_db(
        args.db,
        Options(
            docid=args.docid,
            overwrite=args.overwrite,
            mismatched=args.mismatched,
            max_gap=max_gap,
            dry_run=args.dry_run,
        ),
    )


if __name__ == "__main__":
    main()
