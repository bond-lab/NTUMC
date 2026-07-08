#!/usr/bin/env python3
"""Merge missing corpora from old per-genre databases into live per-language databases.

Three corpora were left behind when the project switched from per-genre
to per-language databases around 2015:

  1. English essay (catb) — 769 sents in work/ntu-mc/2014-04-04/eng-essay.db
  2. Japanese essay (catb) — 773 sents in work/ntu-mc/2014-04-04/jpn-essay.db
  3. Japanese news (kc)   — 2020 sents in work/ntu-mc/2013-10-05/jpn-kc.db

Additionally, Chinese yoursing stype data (2970 entries) exists in
work/ntu-mc/alvas/stype.tab but was never imported.

Usage:
    .venv/bin/python scripts/merge_old_corpora.py --dry-run
    .venv/bin/python scripts/merge_old_corpora.py --fix
    .venv/bin/python scripts/merge_old_corpora.py --fix --download
"""

import argparse
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
WORK_DIR = Path.home() / "work" / "ntu-mc"
SERVER = "compling.upol.cz"
REMOTE_DB_DIR = "/var/www/ntumc/db"

# Old per-genre source databases
ENG_ESSAY_DB = WORK_DIR / "2014-04-04" / "eng-essay.db"
JPN_ESSAY_DB = WORK_DIR / "2014-04-04" / "jpn-essay.db"
JPN_KC_DB = WORK_DIR / "2013-10-05" / "jpn-kc.db"
CMN_STYPE_TAB = WORK_DIR / "alvas" / "stype.tab"


# ---------------------------------------------------------------------------
# Trigger management (following 2015-09-30/renum.py pattern)
# ---------------------------------------------------------------------------


def disable_triggers(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """Drop all triggers and return their definitions for later restore.

    Args:
        conn: Database connection.

    Returns:
        List of (name, table_name, sql) tuples.
    """
    triggers = conn.execute(
        "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    for name, _, _ in triggers:
        conn.execute(f"DROP TRIGGER [{name}]")
    return triggers


def restore_triggers(conn: sqlite3.Connection, triggers: list[tuple[str, str, str]]) -> None:
    """Re-create previously dropped triggers.

    Args:
        conn: Database connection.
        triggers: List from disable_triggers().
    """
    for _, _, sql in triggers:
        if sql:
            conn.executescript(sql)


# ---------------------------------------------------------------------------
# Schema conversion: old concept(sid,wid,cid,...) → concept + cwl
# ---------------------------------------------------------------------------


def convert_old_concepts(
    old_conn: sqlite3.Connection,
    new_conn: sqlite3.Connection,
    sid_offset: int = 0,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Convert old-format concept rows into new concept + cwl rows.

    Old format: concept(sid, wid, cid, clemma, tag, tags, comment)
      — one row per (sid, wid, cid) with wid embedded.
    New format: concept(sid, cid, clemma, tag, tags, comment, ntag, usrname)
      — one row per (sid, cid), MWEs deduplicated.
    Plus:        cwl(sid, wid, cid, usrname)
      — one row per word-concept link.

    Args:
        old_conn: Connection to old per-genre database.
        new_conn: Connection to target per-language database.
        sid_offset: Added to each sid during migration.
        dry_run: If True, count but don't insert.

    Returns:
        (concept_count, cwl_count) inserted.
    """
    rows = old_conn.execute(
        "SELECT sid, wid, cid, clemma, tag, tags, comment FROM concept "
        "WHERE sid IS NOT NULL ORDER BY sid, cid, wid"
    ).fetchall()

    target_cols = [
        c[1] for c in new_conn.execute("PRAGMA table_info(concept)").fetchall()
    ]
    has_ntag = "ntag" in target_cols

    concepts: dict[tuple[int, int], tuple] = {}
    cwl_rows: list[tuple] = []

    for sid, wid, cid, clemma, tag, tags, comment in rows:
        new_sid = sid + sid_offset
        key = (new_sid, cid)
        if key not in concepts:
            if has_ntag:
                concepts[key] = (new_sid, cid, clemma, tag, tags, comment, None, None)
            else:
                concepts[key] = (new_sid, cid, clemma, tag, tags, comment, None)
        cwl_rows.append((new_sid, wid, cid, None))

    if not dry_run:
        if has_ntag:
            concept_sql = (
                "INSERT INTO concept (sid, cid, clemma, tag, tags, comment, ntag, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            )
        else:
            concept_sql = (
                "INSERT INTO concept (sid, cid, clemma, tag, tags, comment, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            )
        new_conn.executemany(concept_sql, concepts.values())
        new_conn.executemany(
            "INSERT INTO cwl (sid, wid, cid, usrname) VALUES (?, ?, ?, ?)",
            cwl_rows,
        )

    return len(concepts), len(cwl_rows)


# ---------------------------------------------------------------------------
# Individual merge operations
# ---------------------------------------------------------------------------


def merge_eng_essay(dry_run: bool = False) -> int:
    """Merge English essay (catb) into eng.db.

    Source: 2014-04-04/eng-essay.db (sid 101–869)
    Target: build/eng.db
    Renumber: sid − 100 (→ 1–769)

    Args:
        dry_run: If True, report but don't modify.

    Returns:
        Number of changes.
    """
    target_db = BUILD_DIR / "eng.db"
    if not ENG_ESSAY_DB.exists():
        logger.error("Source not found: %s", ENG_ESSAY_DB)
        return 0
    if not target_db.exists():
        logger.error("Target not found: %s", target_db)
        return 0

    target = sqlite3.connect(str(target_db))
    existing = target.execute("SELECT COUNT(*) FROM sent WHERE sid < 1000").fetchone()[0]
    if existing > 0:
        logger.info("eng essay: already has %d sents with sid < 1000, skipping", existing)
        target.close()
        return 0

    source = sqlite3.connect(str(ENG_ESSAY_DB))
    sid_offset = -100
    subcorp = source.execute("SELECT * FROM subcorp").fetchone()

    sent_rows = source.execute("SELECT sid, sent, scid, comment FROM sent ORDER BY sid").fetchall()
    word_rows = source.execute(
        "SELECT sid, wid, word, pos, lemma, cfrom, cto, comment FROM word ORDER BY sid, wid"
    ).fetchall()

    new_docid = target.execute("SELECT COALESCE(MAX(docid), 0) + 1 FROM doc").fetchone()[0]
    logger.info(
        "eng essay: %s %d sents, %d words → eng.db (docid=%d, sid offset=%d)",
        "would merge" if dry_run else "merging",
        len(sent_rows), len(word_rows), new_docid, sid_offset,
    )

    if dry_run:
        n_concepts, n_cwl = convert_old_concepts(source, target, sid_offset, dry_run=True)
        logger.info("eng essay: would insert %d concepts, %d cwl rows", n_concepts, n_cwl)
        source.close()
        target.close()
        return len(sent_rows) + len(word_rows) + n_concepts + n_cwl

    triggers = disable_triggers(target)

    target.execute(
        "INSERT INTO corpus (corpusID, corpus, title, language) VALUES (?, ?, ?, ?)",
        (4, "essay", "The Cathedral and the Bazaar", "eng"),
    )
    target.execute(
        "INSERT INTO doc (docid, doc, title, url, subtitle, corpusID) VALUES (?, ?, ?, ?, ?, ?)",
        (new_docid, "catb", "The Cathedral and the Bazaar",
         subcorp[2] if subcorp else None, None, 4),
    )

    target.executemany(
        "INSERT INTO sent (sid, docID, pid, sent, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(sid + sid_offset, new_docid, None, text, comment, None)
         for sid, text, _, comment in sent_rows],
    )
    target.executemany(
        "INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(sid + sid_offset, wid, word, pos, lemma, cfrom, cto, comment, None)
         for sid, wid, word, pos, lemma, cfrom, cto, comment in word_rows],
    )

    n_concepts, n_cwl = convert_old_concepts(source, target, sid_offset)

    target.commit()
    restore_triggers(target, triggers)
    source.close()
    target.close()

    total = 1 + 1 + len(sent_rows) + len(word_rows) + n_concepts + n_cwl
    logger.info("eng essay: inserted %d rows total", total)
    return total


def merge_jpn_essay(dry_run: bool = False) -> int:
    """Merge Japanese essay (catb) into jpn.db.

    Source: 2014-04-04/jpn-essay.db (sid 1–773)
    Target: build/jpn.db
    No renumbering needed.

    Args:
        dry_run: If True, report but don't modify.

    Returns:
        Number of changes.
    """
    target_db = BUILD_DIR / "jpn.db"
    if not JPN_ESSAY_DB.exists():
        logger.error("Source not found: %s", JPN_ESSAY_DB)
        return 0
    if not target_db.exists():
        logger.error("Target not found: %s", target_db)
        return 0

    target = sqlite3.connect(str(target_db))
    existing = target.execute("SELECT COUNT(*) FROM sent WHERE sid < 1000").fetchone()[0]
    if existing > 0:
        logger.info("jpn essay: already has %d sents with sid < 1000, skipping", existing)
        target.close()
        return 0

    source = sqlite3.connect(str(JPN_ESSAY_DB))
    subcorp = source.execute("SELECT * FROM subcorp").fetchone()

    sent_rows = source.execute("SELECT sid, sent, scid, comment FROM sent ORDER BY sid").fetchall()
    word_rows = source.execute(
        "SELECT sid, wid, word, pos, lemma, cfrom, cto, comment FROM word ORDER BY sid, wid"
    ).fetchall()

    new_docid = target.execute("SELECT COALESCE(MAX(docid), 0) + 1 FROM doc").fetchone()[0]
    logger.info(
        "jpn essay: %s %d sents, %d words → jpn.db (docid=%d)",
        "would merge" if dry_run else "merging",
        len(sent_rows), len(word_rows), new_docid,
    )

    if dry_run:
        n_concepts, n_cwl = convert_old_concepts(source, target, 0, dry_run=True)
        logger.info("jpn essay: would insert %d concepts, %d cwl rows", n_concepts, n_cwl)
        source.close()
        target.close()
        return len(sent_rows) + len(word_rows) + n_concepts + n_cwl

    triggers = disable_triggers(target)

    target.execute(
        "INSERT INTO doc (docid, doc, title, url, subtitle, corpusID) VALUES (?, ?, ?, ?, ?, ?)",
        (new_docid, "catb", subcorp[3] if subcorp and len(subcorp) > 3 else "伽藍とバザール",
         subcorp[2] if subcorp else None, None, 1),
    )

    target.executemany(
        "INSERT INTO sent (sid, docID, pid, sent, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(sid, new_docid, None, text, comment, None)
         for sid, text, _, comment in sent_rows],
    )
    target.executemany(
        "INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(sid, wid, word, pos, lemma, cfrom, cto, comment, None)
         for sid, wid, word, pos, lemma, cfrom, cto, comment in word_rows],
    )

    n_concepts, n_cwl = convert_old_concepts(source, target, 0)

    target.commit()
    restore_triggers(target, triggers)
    source.close()
    target.close()

    total = 1 + len(sent_rows) + len(word_rows) + n_concepts + n_cwl
    logger.info("jpn essay: inserted %d rows total", total)
    return total


def merge_jpn_kc(dry_run: bool = False) -> int:
    """Merge Japanese news (kc01 + kc02) into jpn.db.

    Source: 2013-10-05/jpn-kc.db (sid 100000–102019)
    Target: build/jpn.db
    Renumber: sid − 40000 (→ 60000–62019)

    Args:
        dry_run: If True, report but don't modify.

    Returns:
        Number of changes.
    """
    target_db = BUILD_DIR / "jpn.db"
    if not JPN_KC_DB.exists():
        logger.error("Source not found: %s", JPN_KC_DB)
        return 0
    if not target_db.exists():
        logger.error("Target not found: %s", target_db)
        return 0

    target = sqlite3.connect(str(target_db))
    existing = target.execute(
        "SELECT COUNT(*) FROM sent WHERE sid BETWEEN 60000 AND 69999"
    ).fetchone()[0]
    if existing > 0:
        logger.info("jpn kc: already has %d sents in 60000–69999, skipping", existing)
        target.close()
        return 0

    source = sqlite3.connect(str(JPN_KC_DB))
    sid_offset = -40000

    subcorps = source.execute("SELECT * FROM subcorp ORDER BY scid").fetchall()
    sent_rows = source.execute("SELECT sid, sent, scid, comment FROM sent ORDER BY sid").fetchall()
    word_rows = source.execute(
        "SELECT sid, wid, word, pos, lemma, cfrom, cto, comment FROM word ORDER BY sid, wid"
    ).fetchall()

    base_docid = target.execute("SELECT COALESCE(MAX(docid), 0) + 1 FROM doc").fetchone()[0]
    scid_to_docid = {}
    for sc in subcorps:
        scid_to_docid[sc[0]] = base_docid
        base_docid += 1

    logger.info(
        "jpn kc: %s %d sents, %d words, %d subcorpora → jpn.db (sid offset=%d)",
        "would merge" if dry_run else "merging",
        len(sent_rows), len(word_rows), len(subcorps), sid_offset,
    )

    if dry_run:
        n_concepts, n_cwl = convert_old_concepts(source, target, sid_offset, dry_run=True)
        logger.info("jpn kc: would insert %d concepts, %d cwl rows", n_concepts, n_cwl)
        source.close()
        target.close()
        return len(sent_rows) + len(word_rows) + n_concepts + n_cwl

    triggers = disable_triggers(target)

    for sc in subcorps:
        scid = sc[0]
        doc_name = sc[1]
        url = sc[2] if len(sc) > 2 else None
        subtitle = sc[3] if len(sc) > 3 else None
        docid = scid_to_docid[scid]
        title_map = {"kc01": "毎日新聞: 全記事", "kc02": "毎日新聞: 社説記事"}
        title = title_map.get(doc_name, subtitle or doc_name)
        target.execute(
            "INSERT INTO doc (docid, doc, title, url, subtitle, corpusID) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (docid, doc_name, title, url, subtitle, 2),
        )

    target.executemany(
        "INSERT INTO sent (sid, docID, pid, sent, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(sid + sid_offset, scid_to_docid.get(scid, scid_to_docid[1]),
          None, text, comment, None)
         for sid, text, scid, comment in sent_rows],
    )
    target.executemany(
        "INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(sid + sid_offset, wid, word, pos, lemma, cfrom, cto, comment, None)
         for sid, wid, word, pos, lemma, cfrom, cto, comment in word_rows],
    )

    n_concepts, n_cwl = convert_old_concepts(source, target, sid_offset)

    target.commit()
    restore_triggers(target, triggers)
    source.close()
    target.close()

    total = len(subcorps) + len(sent_rows) + len(word_rows) + n_concepts + n_cwl
    logger.info("jpn kc: inserted %d rows total", total)
    return total


def import_cmn_stype(dry_run: bool = False) -> int:
    """Import Chinese yoursing stype data from alvas/stype.tab.

    Source: work/ntu-mc/alvas/stype.tab (H/P values)
    Target: build/cmn.db
    Mapping: H → 'h0', P → 'p'

    Args:
        dry_run: If True, report but don't modify.

    Returns:
        Number of changes.
    """
    target_db = BUILD_DIR / "cmn.db"
    if not CMN_STYPE_TAB.exists():
        logger.error("Source not found: %s", CMN_STYPE_TAB)
        return 0
    if not target_db.exists():
        logger.error("Target not found: %s", target_db)
        return 0

    target = sqlite3.connect(str(target_db))
    existing_stype = target.execute("SELECT COUNT(*) FROM stype").fetchone()[0]
    if existing_stype > 2000:
        logger.info("cmn stype: already has %d stype entries, skipping", existing_stype)
        target.close()
        return 0

    live_sids = {
        r[0] for r in target.execute("SELECT sid FROM sent").fetchall()
    }
    existing_stype_sids = {
        r[0] for r in target.execute("SELECT sid FROM stype").fetchall()
    }

    type_map = {"H": "h0", "P": "p"}
    new_rows = []
    with open(CMN_STYPE_TAB, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < 2 or not parts[0].isdigit():
                continue
            sid = int(parts[0])
            stype = type_map.get(parts[1], parts[1])
            if sid in live_sids and sid not in existing_stype_sids:
                new_rows.append((sid, stype))

    logger.info(
        "cmn stype: %s %d stype entries (from %d in file, %d valid sids)",
        "would import" if dry_run else "importing",
        len(new_rows), sum(1 for _ in open(CMN_STYPE_TAB)), len(live_sids),
    )

    if dry_run:
        target.close()
        return len(new_rows)

    target.executemany("INSERT INTO stype (sid, stype) VALUES (?, ?)", new_rows)
    target.commit()
    target.close()

    logger.info("cmn stype: inserted %d entries", len(new_rows))
    return len(new_rows)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_databases() -> None:
    """Download corpus databases from the compling server."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    for lang in ["eng", "jpn", "cmn"]:
        remote = f"{SERVER}:{REMOTE_DB_DIR}/{lang}.db"
        local = BUILD_DIR / f"{lang}.db"
        logger.info("Downloading %s → %s", remote, local)
        result = subprocess.run(
            ["scp", remote, str(local)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            logger.warning("Failed: %s", result.stderr.strip())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge missing corpora from old per-genre databases."
    )
    parser.add_argument(
        "--download", action="store_true",
        help="Download fresh databases from the server first",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Apply merges to local build/ copies",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would change without modifying files",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if not (args.download or args.fix):
        logger.error("Specify at least one of --download, --fix")
        sys.exit(1)

    if args.download:
        download_databases()

    if args.fix:
        total = 0
        total += merge_eng_essay(dry_run=args.dry_run)
        total += merge_jpn_essay(dry_run=args.dry_run)
        total += merge_jpn_kc(dry_run=args.dry_run)
        total += import_cmn_stype(dry_run=args.dry_run)
        action = "would make" if args.dry_run else "made"
        logger.info("Total: %s %d change(s)", action, total)


if __name__ == "__main__":
    main()
