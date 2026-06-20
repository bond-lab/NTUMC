#!/usr/bin/env python3
"""Test corpus database consistency across all NTU-MC language databases.

Checks schema conformance, referential integrity, and data consistency.
Runs against all .db files in build/ (excluding wordnet databases).

Usage:
    .venv/bin/python scripts/test_corpus.py
    .venv/bin/python scripts/test_corpus.py --lang eng jpn
    .venv/bin/python scripts/test_corpus.py -v          # verbose: show per-DB details
"""

import argparse
import sqlite3
import sys
from pathlib import Path

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

SKIP_DBS = {"wn-ntumc", "wn-multix"}

# ---------------------------------------------------------------------------
# Expected schema (from data/ntumc.sql)
# ---------------------------------------------------------------------------

REQUIRED_TABLES = {
    "meta", "corpus", "doc", "sent", "stype", "word", "concept", "cwl",
}

OPTIONAL_TABLES = {
    "sentiment", "chunks", "xwl", "error", "ewl", "conceptV1",
}

EXPECTED_COLUMNS: dict[str, list[str]] = {
    "meta": ["title", "license", "lang", "version", "master"],
    "corpus": ["corpusID", "corpus", "title", "language"],
    "doc": ["docid", "doc", "title", "url", "subtitle", "corpusID"],
    "sent": ["sid", "docID", "pid", "sent", "comment", "usrname"],
    "stype": ["sid", "stype", "comment"],
    "word": ["sid", "wid", "word", "pos", "lemma", "cfrom", "cto", "comment", "usrname"],
    "concept": ["sid", "cid", "clemma", "tag", "tags", "comment", "usrname"],
    "cwl": ["sid", "wid", "cid", "usrname"],
    "sentiment": ["sid", "cid", "score", "username"],
    "chunks": ["sid", "xid", "score", "comment", "username"],
    "xwl": ["sid", "wid", "xid", "username"],
    "error": ["sid", "eid", "label", "comment", "username"],
    "ewl": ["sid", "wid", "eid", "username"],
}


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


class TestResult:
    """Accumulates pass/fail/warning counts for a single database."""

    def __init__(self, lang: str):
        self.lang = lang
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.messages: list[tuple[str, str, str]] = []

    def ok(self, test: str, detail: str = "") -> None:
        """Record a passing test."""
        self.passed += 1
        self.messages.append(("PASS", test, detail))

    def fail(self, test: str, detail: str) -> None:
        """Record a failing test."""
        self.failed += 1
        self.messages.append(("FAIL", test, detail))

    def warn(self, test: str, detail: str) -> None:
        """Record a warning."""
        self.warnings += 1
        self.messages.append(("WARN", test, detail))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_integrity(conn: sqlite3.Connection, r: TestResult) -> None:
    """Run SQLite integrity check."""
    result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result == "ok":
        r.ok("integrity_check")
    else:
        r.fail("integrity_check", result)


def test_required_tables(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that all required tables exist."""
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for t in sorted(REQUIRED_TABLES):
        if t in tables:
            r.ok(f"table_exists:{t}")
        else:
            r.fail(f"table_exists:{t}", f"required table '{t}' missing")


def test_columns(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that tables have the expected columns."""
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table, expected_cols in EXPECTED_COLUMNS.items():
        if table not in tables:
            continue
        actual_cols = [
            c[1].lower() for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        ]
        for col in expected_cols:
            if col.lower() in actual_cols:
                r.ok(f"column:{table}.{col}")
            else:
                r.fail(f"column:{table}.{col}", f"missing column '{col}' in table '{table}'")


def test_column_types(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check for column type inconsistencies vs the canonical schema."""
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    expected_types = {
        ("stype", "stype"): "TEXT",
        ("stype", "comment"): "TEXT",
        ("meta", "lang"): "TEXT",
        ("meta", "version"): "TEXT",
        ("meta", "master"): "TEXT",
    }
    for (table, col), expected_type in expected_types.items():
        if table not in tables:
            continue
        for c in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            if c[1].lower() == col.lower():
                actual = c[2].upper() if c[2] else "(none)"
                if actual != expected_type:
                    r.warn(
                        f"column_type:{table}.{col}",
                        f"expected {expected_type}, got {actual}",
                    )
                else:
                    r.ok(f"column_type:{table}.{col}")
                break


def test_doc_pk_name(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that doc table PK is named 'docid' (not 'docID')."""
    cols = conn.execute('PRAGMA table_info("doc")').fetchall()
    if not cols:
        return
    pk_col = cols[0][1]
    if pk_col == "docid":
        r.ok("doc_pk_name")
    else:
        r.warn("doc_pk_name", f"doc PK column is '{pk_col}', expected 'docid'")


def test_meta(conn: sqlite3.Connection, r: TestResult, lang: str) -> None:
    """Check meta table has a row and lang matches filename."""
    try:
        meta = conn.execute("SELECT * FROM meta").fetchone()
    except sqlite3.OperationalError:
        r.fail("meta_exists", "meta table not queryable")
        return

    if meta is None:
        r.fail("meta_row", "meta table is empty")
        return
    r.ok("meta_row")

    col_names = [c[1] for c in conn.execute("PRAGMA table_info(meta)").fetchall()]
    if "lang" in col_names:
        idx = col_names.index("lang")
        meta_lang = meta[idx]
        if meta_lang == lang:
            r.ok("meta_lang")
        elif meta_lang is None:
            r.warn("meta_lang", "meta.lang is NULL")
        else:
            r.warn("meta_lang", f"meta.lang='{meta_lang}' != filename '{lang}'")


def test_corpus_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check corpus table referential integrity."""
    # All docs should reference a valid corpus
    orphans = conn.execute("""
        SELECT COUNT(*) FROM doc
        WHERE corpusID IS NOT NULL
          AND corpusID NOT IN (SELECT corpusID FROM corpus)
    """).fetchone()[0]
    if orphans == 0:
        r.ok("doc_corpus_fk")
    else:
        r.fail("doc_corpus_fk", f"{orphans} doc(s) reference non-existent corpusID")

    # Docs with NULL corpusID
    null_corpus = conn.execute(
        "SELECT COUNT(*) FROM doc WHERE corpusID IS NULL"
    ).fetchone()[0]
    if null_corpus == 0:
        r.ok("doc_corpus_notnull")
    else:
        r.warn("doc_corpus_notnull", f"{null_corpus} doc(s) have NULL corpusID")

    # Corpus.language should not be NULL
    null_lang = conn.execute(
        "SELECT COUNT(*) FROM corpus WHERE language IS NULL"
    ).fetchone()[0]
    if null_lang == 0:
        r.ok("corpus_language_notnull")
    else:
        r.fail("corpus_language_notnull", f"{null_lang} corpus row(s) have NULL language")


def test_sent_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check sent.docID references doc.docid."""
    # Get actual doc PK column name (docid or docID)
    doc_cols = [c[1] for c in conn.execute('PRAGMA table_info("doc")').fetchall()]
    pk_col = doc_cols[0] if doc_cols else "docid"

    orphans = conn.execute(f"""
        SELECT COUNT(*) FROM sent
        WHERE docID NOT IN (SELECT "{pk_col}" FROM doc)
    """).fetchone()[0]
    if orphans == 0:
        r.ok("sent_doc_fk")
    else:
        r.fail("sent_doc_fk", f"{orphans} sent(s) reference non-existent doc")


def test_word_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check word.sid references sent.sid."""
    orphans = conn.execute("""
        SELECT COUNT(*) FROM word
        WHERE sid NOT IN (SELECT sid FROM sent)
    """).fetchone()[0]
    if orphans == 0:
        r.ok("word_sent_fk")
    else:
        r.fail("word_sent_fk", f"{orphans} word(s) reference non-existent sent")


def test_concept_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check concept.sid references sent.sid."""
    orphans = conn.execute("""
        SELECT COUNT(*) FROM concept
        WHERE sid NOT IN (SELECT sid FROM sent)
    """).fetchone()[0]
    if orphans == 0:
        r.ok("concept_sent_fk")
    else:
        r.fail("concept_sent_fk", f"{orphans} concept(s) reference non-existent sent")


def test_cwl_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check cwl references: sid→sent, (sid,wid)→word, (sid,cid)→concept."""
    orphan_sent = conn.execute("""
        SELECT COUNT(*) FROM cwl
        WHERE sid NOT IN (SELECT sid FROM sent)
    """).fetchone()[0]
    if orphan_sent == 0:
        r.ok("cwl_sent_fk")
    else:
        r.fail("cwl_sent_fk", f"{orphan_sent} cwl row(s) reference non-existent sent")

    orphan_word = conn.execute("""
        SELECT COUNT(*) FROM cwl c
        LEFT JOIN word w ON w.sid = c.sid AND w.wid = c.wid
        WHERE w.sid IS NULL
    """).fetchone()[0]
    if orphan_word == 0:
        r.ok("cwl_word_fk")
    else:
        r.fail("cwl_word_fk", f"{orphan_word} cwl row(s) reference non-existent word")

    orphan_concept = conn.execute("""
        SELECT COUNT(*) FROM cwl cl
        LEFT JOIN concept co ON co.sid = cl.sid AND co.cid = cl.cid
        WHERE co.sid IS NULL
    """).fetchone()[0]
    if orphan_concept == 0:
        r.ok("cwl_concept_fk")
    else:
        r.fail("cwl_concept_fk", f"{orphan_concept} cwl row(s) reference non-existent concept")


def test_stype_refs(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check stype.sid references sent.sid."""
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "stype" not in tables:
        return
    orphans = conn.execute("""
        SELECT COUNT(*) FROM stype
        WHERE sid NOT IN (SELECT sid FROM sent)
    """).fetchone()[0]
    if orphans == 0:
        r.ok("stype_sent_fk")
    else:
        r.fail("stype_sent_fk", f"{orphans} stype row(s) reference non-existent sent")


def test_sid_uniqueness(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check sent.sid is unique (should be PK)."""
    total = conn.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
    distinct = conn.execute("SELECT COUNT(DISTINCT sid) FROM sent").fetchone()[0]
    if total == distinct:
        r.ok("sent_sid_unique")
    else:
        r.fail("sent_sid_unique", f"{total - distinct} duplicate sid(s)")


def test_word_pk(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check (sid, wid) is unique in word table."""
    total = conn.execute("SELECT COUNT(*) FROM word").fetchone()[0]
    distinct = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT sid, wid FROM word)"
    ).fetchone()[0]
    if total == distinct:
        r.ok("word_sid_wid_unique")
    else:
        r.fail("word_sid_wid_unique", f"{total - distinct} duplicate (sid,wid) pair(s)")


def test_concept_pk(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check (sid, cid) is unique in concept table."""
    total = conn.execute("SELECT COUNT(*) FROM concept").fetchone()[0]
    distinct = conn.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT sid, cid FROM concept)"
    ).fetchone()[0]
    if total == distinct:
        r.ok("concept_sid_cid_unique")
    else:
        r.fail(
            "concept_sid_cid_unique",
            f"{total - distinct} duplicate (sid,cid) pair(s)",
        )


def test_sents_have_words(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that sentences have words (warn if many are empty)."""
    total = conn.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
    if total == 0:
        return
    with_words = conn.execute("""
        SELECT COUNT(DISTINCT s.sid) FROM sent s
        WHERE EXISTS (SELECT 1 FROM word w WHERE w.sid = s.sid)
    """).fetchone()[0]
    empty = total - with_words
    pct = 100 * empty / total
    if empty == 0:
        r.ok("sents_have_words")
    elif pct < 5:
        r.ok("sents_have_words", f"{empty}/{total} empty ({pct:.0f}%)")
    else:
        r.warn("sents_have_words", f"{empty}/{total} sentences have no words ({pct:.0f}%)")


def test_concepts_have_cwl(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that concepts are linked to words via cwl."""
    total = conn.execute("SELECT COUNT(*) FROM concept").fetchone()[0]
    if total == 0:
        return
    linked = conn.execute("""
        SELECT COUNT(DISTINCT c.sid || ':' || c.cid) FROM concept c
        INNER JOIN cwl ON cwl.sid = c.sid AND cwl.cid = c.cid
    """).fetchone()[0]
    unlinked = total - linked
    if unlinked == 0:
        r.ok("concepts_have_cwl")
    else:
        pct = 100 * unlinked / total
        r.warn(
            "concepts_have_cwl",
            f"{unlinked}/{total} concepts ({pct:.0f}%) have no cwl link",
        )


def test_no_null_sids(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check for NULL sids in core tables."""
    for table in ("sent", "word", "concept", "cwl"):
        try:
            nulls = conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE sid IS NULL'
            ).fetchone()[0]
        except sqlite3.OperationalError:
            continue
        if nulls == 0:
            r.ok(f"no_null_sid:{table}")
        else:
            r.fail(f"no_null_sid:{table}", f"{nulls} row(s) with NULL sid")


def test_no_empty_sent_text(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check for sentences with NULL or empty text."""
    empty = conn.execute(
        "SELECT COUNT(*) FROM sent WHERE sent IS NULL OR TRIM(sent) = ''"
    ).fetchone()[0]
    if empty == 0:
        r.ok("no_empty_sent_text")
    else:
        r.warn("no_empty_sent_text", f"{empty} sentence(s) with NULL or empty text")


def test_tag_values(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check concept.tag values are valid synset IDs or known meta-tags."""
    valid_meta = {"e", "w", "x", "per", "org", "loc", "dat", "num", "oth", "nam", "prn"}
    bad = conn.execute("""
        SELECT COUNT(*) FROM concept
        WHERE tag IS NOT NULL AND tag != ''
          AND tag NOT IN ('e','w','x','per','org','loc','dat','num','oth','nam','prn')
          AND tag NOT GLOB '[0-9]*-[nvarsx]'
    """).fetchone()[0]
    if bad == 0:
        r.ok("tag_values")
    else:
        samples = conn.execute("""
            SELECT DISTINCT tag FROM concept
            WHERE tag IS NOT NULL AND tag != ''
              AND tag NOT IN ('e','w','x','per','org','loc','dat','num','oth','nam','prn')
              AND tag NOT GLOB '[0-9]*-[nvarsx]'
            LIMIT 5
        """).fetchall()
        sample_str = ", ".join(repr(s[0]) for s in samples)
        r.warn("tag_values", f"{bad} concept(s) with non-standard tag: {sample_str}")


def test_every_doc_has_sents(conn: sqlite3.Connection, r: TestResult) -> None:
    """Check that every doc has at least one sentence."""
    doc_cols = [c[1] for c in conn.execute('PRAGMA table_info("doc")').fetchall()]
    pk_col = doc_cols[0] if doc_cols else "docid"

    empty_docs = conn.execute(f"""
        SELECT COUNT(*) FROM doc
        WHERE "{pk_col}" NOT IN (SELECT DISTINCT docID FROM sent)
    """).fetchone()[0]
    if empty_docs == 0:
        r.ok("docs_have_sents")
    else:
        r.warn("docs_have_sents", f"{empty_docs} doc(s) have no sentences")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_tests(db_path: Path) -> TestResult:
    """Run all tests on a single database.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        TestResult with all findings.
    """
    lang = db_path.stem
    r = TestResult(lang)

    conn = sqlite3.connect(str(db_path))

    test_integrity(conn, r)
    test_required_tables(conn, r)
    test_columns(conn, r)
    test_column_types(conn, r)
    test_doc_pk_name(conn, r)
    test_meta(conn, r, lang)
    test_corpus_refs(conn, r)
    test_sent_refs(conn, r)
    test_word_refs(conn, r)
    test_concept_refs(conn, r)
    test_cwl_refs(conn, r)
    test_stype_refs(conn, r)
    test_sid_uniqueness(conn, r)
    test_word_pk(conn, r)
    test_concept_pk(conn, r)
    test_sents_have_words(conn, r)
    test_concepts_have_cwl(conn, r)
    test_no_null_sids(conn, r)
    test_no_empty_sent_text(conn, r)
    test_tag_values(conn, r)
    test_every_doc_has_sents(conn, r)

    conn.close()
    return r


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description="Test corpus database consistency.")
    parser.add_argument(
        "--lang", nargs="+",
        help="Languages to test (default: all in build/)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show all test results, not just failures and warnings",
    )
    args = parser.parse_args()

    link_db_stems = {
        p.stem for p in BUILD_DIR.glob("*-*.db") if p.stem not in SKIP_DBS
    }
    if args.lang:
        db_paths = [BUILD_DIR / f"{lang}.db" for lang in args.lang]
    else:
        db_paths = sorted(
            p for p in BUILD_DIR.glob("*.db")
            if p.stem not in SKIP_DBS and p.stem not in link_db_stems
        )

    total_pass = 0
    total_fail = 0
    total_warn = 0

    for db_path in db_paths:
        if not db_path.exists():
            print(f"SKIP {db_path.stem}: not found")
            continue

        r = run_tests(db_path)
        total_pass += r.passed
        total_fail += r.failed
        total_warn += r.warnings

        status = "FAIL" if r.failed else ("WARN" if r.warnings else "OK")
        print(f"\n{status} {r.lang}.db — {r.passed} passed, {r.failed} failed, {r.warnings} warnings")

        for level, test, detail in r.messages:
            if level == "FAIL":
                print(f"  FAIL  {test}: {detail}")
            elif level == "WARN":
                print(f"  WARN  {test}: {detail}")
            elif args.verbose and detail:
                print(f"  ok    {test}: {detail}")

    print(f"\n{'=' * 60}")
    print(f"Total: {total_pass} passed, {total_fail} failed, {total_warn} warnings")
    print(f"{'=' * 60}")

    sys.exit(1 if total_fail > 0 else 0)


if __name__ == "__main__":
    main()
