#!/usr/bin/env python3
"""Audit and fix corpus metadata: corpus table, doc.corpusID, and stype.

Downloads fresh copies from the compling server, applies fixes, and
produces an audit report.  Changes are applied to local copies only;
push back to the server manually after review.

Usage:
    # Audit only (no changes)
    .venv/bin/python scripts/fix_corpus.py --audit

    # Download fresh copies and audit
    .venv/bin/python scripts/fix_corpus.py --download --audit

    # Apply fixes to local build/ copies
    .venv/bin/python scripts/fix_corpus.py --fix

    # Download, fix, and audit
    .venv/bin/python scripts/fix_corpus.py --download --fix --audit

    # Push fixed databases back to server (interactive confirmation)
    .venv/bin/python scripts/fix_corpus.py --push
"""

import argparse
import logging
import sqlite3
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
SERVER = "compling.upol.cz"
REMOTE_DB_DIR = "/var/www/ntumc/db"

CORE_LANGS = ["eng", "cmn", "jpn", "ind", "ita", "ces", "zsm", "yue"]

# ---------------------------------------------------------------------------
# Expected corpus structure per language (from the NTU-MC manual).
# {corpusID: (short_name, title)}
# Only entries that SHOULD exist are listed; missing ones will be created.
# ---------------------------------------------------------------------------

EXPECTED_CORPORA: dict[str, dict[int, tuple[str, str]]] = {
    "eng": {
        1: ("kc", "Kyoto University Text Corpus: Mainichi Shimbun"),
        2: ("yoursing", "Singapore Tourism: Your Singapore"),
        3: ("story", "Short Stories"),
        4: ("essay", "The Cathedral and the Bazaar"),
    },
    "cmn": {
        1: ("essay", "随笔"),  # 随笔
        2: ("kc", "京都大学文本语料库："
                   "每日报纸"),  # 京都大学文本语料库：每日报纸
        3: ("story", "短篇小說"),  # 短篇小說
        4: ("yoursing", "Singapore Tourism: Your Singapore"),
    },
    "jpn": {
        1: ("essay", " 随筆"),  # 随筆 (leading space preserved from DB)
        2: ("kc", "新聞"),  # 新聞
        3: ("story", "小説"),  # 小説
        4: ("yoursing", "ユア・シンガポール"),
        5: ("gloss", "定義文"),  # 定義文
    },
    "ind": {
        1: ("essay", "Esai"),
        2: ("story", "Cerita Pendek"),
        3: ("story", "Cerita Pendek"),  # alias — docs with corpusID=3 are stories
        4: ("yoursing", "Your Singapore"),
        5: ("gloss", "gloss"),
    },
    "ita": {
        1: ("story", "Novella"),
    },
    "ces": {
        3: ("story", "Povídky"),  # Povídky
    },
    "zsm": {
        1: ("kc", "Kyoto University Text Corpus: Mainichi Shimbun"),
        2: ("yoursing", "Singapore Tourism: Your Singapore"),
        3: ("story", "Short Stories"),
    },
    "yue": {
        6: ("comments", "評論"),  # 評論
    },
}

# ---------------------------------------------------------------------------
# stype inference from sentence content
# ---------------------------------------------------------------------------

# For yoursing corpora: first sentence of each doc is the title (h0 in jpn/ind).
# For stories: paragraph breaks can be inferred from blank lines or
#   sentence patterns, but that requires careful per-document work.


def infer_yoursing_stype(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Infer stype for YourSingapore documents.

    Marks the first sentence of each document as 'h0' (document title).

    Args:
        conn: Database connection.

    Returns:
        List of (sid, stype) tuples to insert.
    """
    rows = conn.execute("""
        SELECT s.sid, s.docID,
               ROW_NUMBER() OVER (PARTITION BY s.docID ORDER BY s.sid) AS rn
        FROM sent s
        JOIN doc d ON s.docID = d.docid
        JOIN corpus c ON d.corpusID = c.corpusID
        WHERE c.corpus = 'yoursing'
    """).fetchall()

    existing = {
        r[0]
        for r in conn.execute("SELECT sid FROM stype").fetchall()
    }

    new_stypes = []
    for sid, _, rn in rows:
        if sid in existing:
            continue
        if rn == 1:
            new_stypes.append((sid, "h0"))

    return new_stypes


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def download_databases() -> None:
    """Download corpus databases from the compling server."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    for lang in CORE_LANGS:
        remote = f"{SERVER}:{REMOTE_DB_DIR}/{lang}.db"
        local = BUILD_DIR / f"{lang}.db"
        logger.info("Downloading %s → %s", remote, local)
        result = subprocess.run(
            ["scp", remote, str(local)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("Failed to download %s: %s", remote, result.stderr.strip())


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def audit_database(db_path: Path) -> dict:
    """Audit a single language database for metadata issues.

    Args:
        db_path: Path to the database.

    Returns:
        Dict with audit findings.
    """
    lang = db_path.stem
    findings: dict = {"lang": lang, "issues": []}

    if not db_path.exists():
        findings["issues"].append(("MISSING", f"{db_path} does not exist"))
        return findings

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # 1. Check corpus table completeness
    expected = EXPECTED_CORPORA.get(lang, {})
    existing_ids = {
        r["corpusID"]
        for r in conn.execute("SELECT corpusID FROM corpus").fetchall()
    }

    for cid, (cname, ctitle) in expected.items():
        if cid not in existing_ids:
            findings["issues"].append(
                ("CORPUS_MISSING", f"corpusID={cid} ({cname}: {ctitle}) not in corpus table")
            )

    # 2. Check doc.corpusID references
    orphan_docs = conn.execute("""
        SELECT d.docid, d.doc, d.corpusID
        FROM doc d
        WHERE d.corpusID IS NOT NULL
          AND d.corpusID NOT IN (SELECT corpusID FROM corpus)
    """).fetchall()
    for row in orphan_docs:
        findings["issues"].append(
            ("DOC_ORPHAN", f"doc {row['docid']} ({row['doc']}) has corpusID={row['corpusID']} "
                           f"with no matching corpus row")
        )

    null_corpus_docs = conn.execute(
        "SELECT docid, doc FROM doc WHERE corpusID IS NULL"
    ).fetchall()
    for row in null_corpus_docs:
        findings["issues"].append(
            ("DOC_NULL_CORPUS", f"doc {row['docid']} ({row['doc']}) has NULL corpusID")
        )

    # 3. Check corpus rows with no documents
    empty_corpora = conn.execute("""
        SELECT c.corpusID, c.corpus, c.title
        FROM corpus c
        WHERE c.corpusID NOT IN (SELECT DISTINCT corpusID FROM doc WHERE corpusID IS NOT NULL)
    """).fetchall()
    for row in empty_corpora:
        findings["issues"].append(
            ("CORPUS_EMPTY", f"corpus {row['corpusID']} ({row['corpus']}: {row['title']}) "
                             f"has no documents")
        )

    # 4. Check meta table
    meta = conn.execute("SELECT * FROM meta").fetchone()
    if meta:
        meta_lang = meta["lang"] if "lang" in meta.keys() else None
        if meta_lang and meta_lang != lang:
            findings["issues"].append(
                ("META_LANG", f"meta.lang='{meta_lang}' does not match filename '{lang}'")
            )
    else:
        findings["issues"].append(("META_MISSING", "meta table is empty"))

    # 5. Check ces.corpus.language
    if lang == "ces":
        row = conn.execute(
            "SELECT corpusID, language FROM corpus WHERE language IS NULL"
        ).fetchone()
        if row:
            findings["issues"].append(
                ("CORPUS_NULL_LANG", f"corpus {row['corpusID']} has NULL language")
            )

    # 6. stype coverage
    total_sents = conn.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
    stype_sents = conn.execute("SELECT COUNT(DISTINCT sid) FROM stype").fetchone()[0]
    findings["stype_coverage"] = (stype_sents, total_sents)

    corpus_stype = conn.execute("""
        SELECT d.corpusID, COALESCE(c.corpus, '???'),
               COUNT(DISTINCT s.sid), COUNT(DISTINCT st.sid)
        FROM sent s
        JOIN doc d ON s.docID = d.docid
        LEFT JOIN corpus c ON d.corpusID = c.corpusID
        LEFT JOIN stype st ON st.sid = s.sid
        GROUP BY d.corpusID
        ORDER BY d.corpusID
    """).fetchall()
    for cid, cname, total, typed in corpus_stype:
        if typed == 0 and total > 0:
            findings["issues"].append(
                ("STYPE_MISSING", f"corpus {cid} ({cname}): 0/{total} sentences have stype")
            )
        elif typed < total and total > 0:
            pct = 100 * typed / total
            findings["issues"].append(
                ("STYPE_PARTIAL", f"corpus {cid} ({cname}): {typed}/{total} ({pct:.0f}%) "
                                  f"sentences have stype")
            )

    conn.close()
    return findings


def print_audit(all_findings: list[dict]) -> None:
    """Print a formatted audit report.

    Args:
        all_findings: List of per-language audit dicts.
    """
    print()
    print("=" * 70)
    print("  CORPUS METADATA AUDIT")
    print("=" * 70)

    total_issues = 0
    for f in all_findings:
        lang = f["lang"]
        issues = f["issues"]
        total_issues += len(issues)

        print(f"\n  {lang}.db", end="")
        if not issues:
            print(" — OK")
            continue

        print(f" — {len(issues)} issue(s):")
        for severity, msg in issues:
            marker = {
                "CORPUS_MISSING": "FIX",
                "DOC_ORPHAN": "FIX",
                "CORPUS_EMPTY": "INFO",
                "CORPUS_NULL_LANG": "FIX",
                "STYPE_MISSING": "TODO",
                "STYPE_PARTIAL": "INFO",
                "DOC_NULL_CORPUS": "FIX",
                "META_LANG": "INFO",
                "META_MISSING": "INFO",
                "MISSING": "ERR",
            }.get(severity, severity)
            print(f"    [{marker:4s}] {msg}")

        if "stype_coverage" in f:
            typed, total = f["stype_coverage"]
            pct = 100 * typed / total if total else 0
            print(f"    stype: {typed}/{total} ({pct:.0f}%)")

    print(f"\n  Total: {total_issues} issue(s) across {len(all_findings)} database(s)")
    print()


# ---------------------------------------------------------------------------
# Fixes
# ---------------------------------------------------------------------------


def fix_database(db_path: Path, dry_run: bool = False) -> int:
    """Apply metadata fixes to a single language database.

    Fixes applied:
    1. Add missing corpus rows from EXPECTED_CORPORA.
    2. Fix doc.corpusID references (ind: corpusID=3 → ensure corpus row exists).
    3. Fix NULL language in corpus table (ces).
    4. Add stype='h0' for first sentence of each yoursing document.

    Args:
        db_path: Path to the database.
        dry_run: If True, report what would change but don't modify.

    Returns:
        Number of changes made (or would-be-made in dry_run).
    """
    lang = db_path.stem
    if not db_path.exists():
        logger.warning("Skipping %s: file not found", db_path)
        return 0

    conn = sqlite3.connect(str(db_path))
    changes = 0

    # 1. Add missing corpus rows
    expected = EXPECTED_CORPORA.get(lang, {})
    existing = {
        r[0]: r[1:]
        for r in conn.execute(
            "SELECT corpusID, corpus, title, language FROM corpus"
        ).fetchall()
    }

    for cid, (cname, ctitle) in expected.items():
        if cid not in existing:
            logger.info(
                "%s: %s corpus row corpusID=%d (%s: %s)",
                lang, "would add" if dry_run else "adding", cid, cname, ctitle,
            )
            if not dry_run:
                conn.execute(
                    "INSERT INTO corpus (corpusID, corpus, title, language) VALUES (?, ?, ?, ?)",
                    (cid, cname, ctitle, lang),
                )
            changes += 1

    # 2. Fix NULL language in corpus table
    null_lang_rows = conn.execute(
        "SELECT corpusID, corpus FROM corpus WHERE language IS NULL"
    ).fetchall()
    for cid, cname in null_lang_rows:
        logger.info(
            "%s: %s corpus.language for corpusID=%d (%s) → '%s'",
            lang, "would set" if dry_run else "setting", cid, cname, lang,
        )
        if not dry_run:
            conn.execute(
                "UPDATE corpus SET language = ? WHERE corpusID = ?", (lang, cid)
            )
        changes += 1

    # 3. Add stype for yoursing documents (h0 for doc title)
    new_stypes = infer_yoursing_stype(conn)
    if new_stypes:
        logger.info(
            "%s: %s %d stype entries for yoursing doc titles (h0)",
            lang, "would add" if dry_run else "adding", len(new_stypes),
        )
        if not dry_run:
            conn.executemany(
                "INSERT INTO stype (sid, stype) VALUES (?, ?)", new_stypes
            )
        changes += len(new_stypes)

    if not dry_run and changes > 0:
        conn.commit()
        logger.info("%s: committed %d change(s)", lang, changes)

    conn.close()
    return changes


# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------


def push_databases() -> None:
    """Push fixed databases back to the server (with confirmation)."""
    print("\nDatabases to push:")
    for lang in CORE_LANGS:
        local = BUILD_DIR / f"{lang}.db"
        if local.exists():
            print(f"  {local} → {SERVER}:{REMOTE_DB_DIR}/{lang}.db")

    answer = input("\nPush these to the server? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    for lang in CORE_LANGS:
        local = BUILD_DIR / f"{lang}.db"
        if not local.exists():
            continue
        remote = f"{SERVER}:{REMOTE_DB_DIR}/{lang}.db"
        logger.info("Pushing %s → %s", local, remote)
        result = subprocess.run(
            ["scp", str(local), remote],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Failed to push %s: %s", local, result.stderr.strip())
        else:
            logger.info("  OK")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Audit and fix corpus metadata (corpus table, doc.corpusID, stype)."
    )
    parser.add_argument(
        "--download", action="store_true",
        help="Download fresh databases from the compling server",
    )
    parser.add_argument(
        "--audit", action="store_true",
        help="Print an audit report of all issues",
    )
    parser.add_argument(
        "--fix", action="store_true",
        help="Apply automated fixes to local build/ copies",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="With --fix, report what would change without modifying files",
    )
    parser.add_argument(
        "--push", action="store_true",
        help="Push fixed databases back to the server (interactive confirmation)",
    )
    parser.add_argument(
        "--lang", nargs="+", default=CORE_LANGS,
        help=f"Languages to process (default: {' '.join(CORE_LANGS)})",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    if not (args.download or args.audit or args.fix or args.push):
        logger.error("Specify at least one of --download, --audit, --fix, --push")
        sys.exit(1)

    if args.download:
        download_databases()

    if args.fix:
        total = 0
        for lang in args.lang:
            db_path = BUILD_DIR / f"{lang}.db"
            total += fix_database(db_path, dry_run=args.dry_run)
        action = "would make" if args.dry_run else "made"
        logger.info("Total: %s %d change(s)", action, total)

    if args.audit:
        all_findings = []
        for lang in args.lang:
            db_path = BUILD_DIR / f"{lang}.db"
            all_findings.append(audit_database(db_path))
        print_audit(all_findings)

    if args.push:
        push_databases()


if __name__ == "__main__":
    main()
