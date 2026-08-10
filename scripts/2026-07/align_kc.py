#!/usr/bin/env python3
"""Create slinks and stypes for kc01/kc02 using article IDs in sent comments.

The kc (Mainichi Shimbun) sentences have comments like ``s=95010100301;``
where the digits encode date (YYMMDD), article number (AAA), and sentence
number (SS).  Sentences sharing the same article ID are parallel across
languages, and sentence 01 marks a paragraph start.

This script:
  1. Creates eng↔jpn and eng↔cmn slinks by matching article+sentence IDs
  2. Sets stype='p' for sentence 01 of each article (paragraph start)
  3. Sets stype='h0' for the first sentence of each doc (title)

Usage:
    .venv/bin/python scripts/align_kc.py --dry-run
    .venv/bin/python scripts/align_kc.py --fix
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
KC_DOCS = ("kc01", "kc02")
LANGS = ("eng", "jpn", "cmn")
COMMENT_RE = re.compile(r"s=(\d+);")


def parse_comment(comment: str) -> tuple[str, int] | None:
    """Parse article key and sentence number from a sent comment.

    Args:
        comment: Sentence comment string, e.g. ``s=95010100301;``.

    Returns:
        (article_key, sentence_number) or None if unparseable.
    """
    if not comment:
        return None
    m = COMMENT_RE.search(comment)
    if not m:
        return None
    val = m.group(1)
    if len(val) < 4:
        return None
    return val[:-2], int(val[-2:])


def load_kc_sents(lang: str) -> dict[str, list[tuple[int, int]]]:
    """Load kc sentences grouped by article key.

    Args:
        lang: Language code.

    Returns:
        {article_key: [(sent_num, sid), ...]} sorted by sent_num.
    """
    conn = sqlite3.connect(str(BUILD_DIR / f"{lang}.db"))
    articles: dict[str, list[tuple[int, int]]] = {}

    for doc in KC_DOCS:
        row = conn.execute(
            "SELECT MIN(s.sid), MAX(s.sid) FROM sent s "
            "JOIN doc d ON s.docID=d.docid WHERE d.doc=?",
            (doc,),
        ).fetchone()
        if not row or row[0] is None:
            continue
        smin, smax = row
        for sid, comment in conn.execute(
            "SELECT sid, comment FROM sent WHERE sid BETWEEN ? AND ?",
            (smin, smax),
        ).fetchall():
            parsed = parse_comment(comment)
            if parsed:
                art_key, sent_num = parsed
                articles.setdefault(art_key, []).append((sent_num, sid))

    conn.close()
    for sents in articles.values():
        sents.sort()
    return articles


def build_slinks(
    eng_articles: dict[str, list[tuple[int, int]]],
    tgt_articles: dict[str, list[tuple[int, int]]],
) -> list[tuple[int, int]]:
    """Build (eng_sid, tgt_sid) pairs by matching article+sentence IDs.

    Args:
        eng_articles: English articles from load_kc_sents.
        tgt_articles: Target language articles.

    Returns:
        List of (eng_sid, tgt_sid) pairs.
    """
    pairs = []
    for art_key, eng_sents in eng_articles.items():
        tgt_sents = tgt_articles.get(art_key)
        if not tgt_sents:
            continue
        tgt_by_num = {num: sid for num, sid in tgt_sents}
        for num, eng_sid in eng_sents:
            tgt_sid = tgt_by_num.get(num)
            if tgt_sid is not None:
                pairs.append((eng_sid, tgt_sid))
    pairs.sort()
    return pairs


def insert_slinks(
    link_db: Path,
    pairs: list[tuple[int, int]],
    dry_run: bool,
) -> int:
    """Insert slinks into a link database, creating it if needed.

    Args:
        link_db: Path to the link database.
        pairs: List of (fsid, tsid) pairs.
        dry_run: If True, count but don't insert.

    Returns:
        Number of new slinks inserted.
    """
    conn = sqlite3.connect(str(link_db))

    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "slink" not in tables:
        if dry_run:
            conn.close()
            return len(pairs)
        conn.execute(
            "CREATE TABLE slink ("
            "slid INTEGER PRIMARY KEY, "
            "fsid INTEGER NOT NULL, tsid INTEGER NOT NULL, "
            "ltype TEXT, conf FLOAT, comment TEXT, usrname TEXT, "
            "UNIQUE(fsid, tsid) ON CONFLICT IGNORE)"
        )

    existing = set(
        (r[0], r[1])
        for r in conn.execute("SELECT fsid, tsid FROM slink").fetchall()
    )

    new_pairs = [(f, t) for f, t in pairs if (f, t) not in existing]
    if not new_pairs:
        conn.close()
        return 0

    if not dry_run:
        max_slid = conn.execute(
            "SELECT COALESCE(MAX(slid), 0) FROM slink"
        ).fetchone()[0]
        rows = [
            (max_slid + i + 1, f, t, None, 1.0, "aligned by article ID", None)
            for i, (f, t) in enumerate(new_pairs)
        ]
        conn.executemany(
            "INSERT INTO slink (slid, fsid, tsid, ltype, conf, comment, usrname) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()

    conn.close()
    return len(new_pairs)


def insert_stypes(
    lang: str,
    articles: dict[str, list[tuple[int, int]]],
    dry_run: bool,
) -> int:
    """Insert paragraph-start stypes for sentence 01 of each article.

    Args:
        lang: Language code.
        articles: Articles from load_kc_sents.
        dry_run: If True, count but don't insert.

    Returns:
        Number of new stypes inserted.
    """
    conn = sqlite3.connect(str(BUILD_DIR / f"{lang}.db"))
    existing = set(
        r[0] for r in conn.execute("SELECT sid FROM stype").fetchall()
    )

    new_stypes = []
    for sents in articles.values():
        for num, sid in sents:
            if num == 1 and sid not in existing:
                new_stypes.append((sid, "p"))

    if new_stypes and not dry_run:
        conn.executemany(
            "INSERT OR IGNORE INTO stype (sid, stype) VALUES (?, ?)",
            new_stypes,
        )
        conn.commit()

    conn.close()
    return len(new_stypes)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Create slinks and stypes for kc01/kc02 from article IDs."
    )
    parser.add_argument("--fix", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    action = "would" if args.dry_run else "will"

    # Load articles per language
    all_articles: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for lang in LANGS:
        db_path = BUILD_DIR / f"{lang}.db"
        if not db_path.exists():
            continue
        all_articles[lang] = load_kc_sents(lang)
        n_arts = len(all_articles[lang])
        n_sents = sum(len(s) for s in all_articles[lang].values())
        logger.info(
            "%s: %d articles, %d sentences with article IDs",
            lang, n_arts, n_sents,
        )

    if "eng" not in all_articles:
        logger.error("eng.db not found or has no kc data")
        sys.exit(1)

    # Create slinks
    logger.info("")
    logger.info("=== Sentence links ===")
    for tgt_lang in LANGS:
        if tgt_lang == "eng" or tgt_lang not in all_articles:
            continue
        pairs = build_slinks(all_articles["eng"], all_articles[tgt_lang])
        link_db = BUILD_DIR / f"eng-{tgt_lang}.db"
        n = insert_slinks(link_db, pairs, dry_run=args.dry_run)
        logger.info(
            "  eng→%s: %s insert %d slinks (of %d matched)",
            tgt_lang, action, n, len(pairs),
        )

    # Create stypes
    logger.info("")
    logger.info("=== Paragraph stypes ===")
    for lang in LANGS:
        if lang not in all_articles:
            continue
        n = insert_stypes(lang, all_articles[lang], dry_run=args.dry_run)
        logger.info("  %s: %s insert %d paragraph stypes", lang, action, n)

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
