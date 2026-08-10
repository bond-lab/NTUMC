#!/usr/bin/env python3
"""Audit annotation coverage across all NTU-MC database versions.

Scans every .db file under ~/work/ntu-mc/ and the current build databases
in build/, then compares tagged-concept counts per document and language.
Flags documents where the current build has fewer annotations than any
older version.

Usage:
    .venv/bin/python scripts/audit_annotations.py
"""

import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
OLD_ROOT = Path.home() / "work" / "ntu-mc"

# Tags that do not count as real annotations.
SKIP_TAGS: frozenset[str] = frozenset({"x", "w", "e", ""})

# Known three-letter language codes for filename-based detection.
_KNOWN_LANGS: frozenset[str] = frozenset({
    "eng", "jpn", "cmn", "ind", "ita", "ces", "kor", "vie",
    "tha", "yue", "zsm", "mya", "enc",
})

# Build DBs to scan (lang code -> filename).
BUILD_LANGS: list[str] = ["eng", "jpn", "cmn", "ind", "ita", "ces"]


@dataclass
class DocStats:
    """Annotation statistics for a single document in one database."""

    sentences: int = 0
    words: int = 0
    tagged_concepts: int = 0
    distinct_tags: int = 0


@dataclass
class SourceRecord:
    """A doc's stats tied to the database they came from."""

    db_path: str
    stats: DocStats = field(default_factory=DocStats)


def _table_names(con: sqlite3.Connection) -> set[str]:
    """Return the set of table names in an SQLite database."""
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def _column_names(con: sqlite3.Connection, table: str) -> list[str]:
    """Return column names for *table*."""
    return [row[1] for row in con.execute(f"PRAGMA table_info({table})")]


def _extract_lang(con: sqlite3.Connection, db_path: Path) -> str:
    """Best-effort language code from the meta table or the filename.

    Args:
        con: Open database connection.
        db_path: Path to the .db file.

    Returns:
        Three-letter language code, or "unk" if undetermined.
    """
    try:
        meta_cols = _column_names(con, "meta")
        if "lang" in meta_cols:
            row = con.execute("SELECT lang FROM meta LIMIT 1").fetchone()
            if row and row[0]:
                return row[0]
        if "language" in meta_cols:
            row = con.execute("SELECT language FROM meta LIMIT 1").fetchone()
            if row and row[0]:
                lang = row[0].strip().lstrip("-")
                if len(lang) == 3:
                    return lang
    except sqlite3.OperationalError:
        pass
    # Fall back to filename: e.g. "eng-story.db" -> "eng", "cmn.db" -> "cmn",
    # "enga.db" -> "eng", "eng1A.db" -> "eng", "indE.db" -> "ind"
    stem = db_path.stem
    lang_part = stem.split("-")[0]
    if len(lang_part) == 3 and lang_part.isalpha():
        return lang_part
    # Try extracting a 3-letter prefix from names like "enga", "eng1A", "indE"
    if len(lang_part) > 3 and lang_part[:3].isalpha():
        candidate = lang_part[:3]
        if candidate in _KNOWN_LANGS:
            return candidate
    return "unk"


def _stats_with_doc_table(
    con: sqlite3.Connection, tables: set[str]
) -> dict[str, DocStats]:
    """Gather per-doc stats from a DB that has a ``doc`` table.

    Args:
        con: Open database connection.
        tables: Set of table names present.

    Returns:
        Mapping of doc name to DocStats.
    """
    results: dict[str, DocStats] = {}
    has_word = "word" in tables
    sent_cols = _column_names(con, "sent")
    doc_id_col = "docID" if "docID" in sent_cols else "docid"

    # -- sentences per doc --
    rows = con.execute(f"""
        SELECT d.doc, COUNT(s.sid)
        FROM doc d
        LEFT JOIN sent s ON s.{doc_id_col} = d.docid
        GROUP BY d.doc
    """).fetchall()
    for doc_name, n_sents in rows:
        if not doc_name:
            continue
        results.setdefault(doc_name, DocStats()).sentences = n_sents

    # -- words per doc --
    if has_word:
        rows = con.execute(f"""
            SELECT d.doc, COUNT(w.wid)
            FROM doc d
            JOIN sent s ON s.{doc_id_col} = d.docid
            JOIN word w ON w.sid = s.sid
            GROUP BY d.doc
        """).fetchall()
        for doc_name, n_words in rows:
            if doc_name and doc_name in results:
                results[doc_name].words = n_words

    # -- tagged concepts per doc --
    rows = con.execute(f"""
        SELECT d.doc,
               COUNT(c.cid),
               COUNT(DISTINCT c.tag)
        FROM doc d
        JOIN sent s ON s.{doc_id_col} = d.docid
        JOIN concept c ON c.sid = s.sid
        WHERE c.tag NOT IN ('x', 'w', 'e', '')
          AND c.tag IS NOT NULL
        GROUP BY d.doc
    """).fetchall()
    for doc_name, n_tagged, n_distinct in rows:
        if doc_name and doc_name in results:
            results[doc_name].tagged_concepts = n_tagged
            results[doc_name].distinct_tags = n_distinct

    return results


def _stats_with_subcorp(
    con: sqlite3.Connection, tables: set[str]
) -> dict[str, DocStats]:
    """Gather per-subcorpus stats from a DB that has a ``subcorp`` table.

    The subcorpus name is used as the doc identifier.

    Args:
        con: Open database connection.
        tables: Set of table names present.

    Returns:
        Mapping of subcorpus name to DocStats.
    """
    results: dict[str, DocStats] = {}
    has_word = "word" in tables

    rows = con.execute("""
        SELECT sc.subcorpus, COUNT(s.sid)
        FROM subcorp sc
        LEFT JOIN sent s ON s.scid = sc.scid
        GROUP BY sc.subcorpus
    """).fetchall()
    for name, n_sents in rows:
        if not name:
            continue
        results.setdefault(name, DocStats()).sentences = n_sents

    if has_word:
        rows = con.execute("""
            SELECT sc.subcorpus, COUNT(w.wid)
            FROM subcorp sc
            JOIN sent s ON s.scid = sc.scid
            JOIN word w ON w.sid = s.sid
            GROUP BY sc.subcorpus
        """).fetchall()
        for name, n_words in rows:
            if name and name in results:
                results[name].words = n_words

    rows = con.execute("""
        SELECT sc.subcorpus,
               COUNT(c.cid),
               COUNT(DISTINCT c.tag)
        FROM subcorp sc
        JOIN sent s ON s.scid = sc.scid
        JOIN concept c ON c.sid = s.sid
        WHERE c.tag NOT IN ('x', 'w', 'e', '')
          AND c.tag IS NOT NULL
        GROUP BY sc.subcorpus
    """).fetchall()
    for name, n_tagged, n_distinct in rows:
        if name and name in results:
            results[name].tagged_concepts = n_tagged
            results[name].distinct_tags = n_distinct

    return results


def _stats_single_doc(
    con: sqlite3.Connection, tables: set[str], doc_name: str
) -> dict[str, DocStats]:
    """Gather stats for a DB that represents a single document.

    The entire database is treated as one document with the given name.

    Args:
        con: Open database connection.
        tables: Set of table names present.
        doc_name: Name to assign to this single-document database.

    Returns:
        Mapping with one entry (doc_name -> DocStats).
    """
    has_word = "word" in tables
    st = DocStats()

    st.sentences = con.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
    if has_word:
        st.words = con.execute("SELECT COUNT(*) FROM word").fetchone()[0]

    row = con.execute("""
        SELECT COUNT(cid), COUNT(DISTINCT tag)
        FROM concept
        WHERE tag NOT IN ('x', 'w', 'e', '')
          AND tag IS NOT NULL
    """).fetchone()
    st.tagged_concepts = row[0]
    st.distinct_tags = row[1]

    return {doc_name: st}


def _derive_doc_name(db_path: Path) -> str:
    """Derive a doc name from a per-genre DB filename.

    For example, ``eng-catb.db`` -> ``catb``, ``cmn-dm.db`` -> ``dm``.

    Args:
        db_path: Path to the database file.

    Returns:
        Short document name extracted from the filename.
    """
    stem = db_path.stem
    parts = stem.split("-", 1)
    if len(parts) == 2:
        return parts[1]
    return stem


def _relative_label(db_path: Path) -> str:
    """Create a short label for a DB path relative to OLD_ROOT or BUILD_DIR.

    Args:
        db_path: Absolute path to the database file.

    Returns:
        Short relative label string.
    """
    try:
        return str(db_path.relative_to(OLD_ROOT))
    except ValueError:
        pass
    try:
        return "build/" + str(db_path.relative_to(BUILD_DIR))
    except ValueError:
        pass
    return str(db_path)


def scan_database(db_path: Path) -> list[tuple[str, str, str, DocStats]]:
    """Scan a single database and return per-doc annotation stats.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        List of (lang, doc_name, db_label, DocStats) tuples.
    """
    label = _relative_label(db_path)

    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        logger.debug("Cannot open %s: %s", label, exc)
        return []

    try:
        tables = _table_names(con)

        # Skip link databases (slink but no doc/concept)
        if "slink" in tables and "concept" not in tables:
            logger.debug("Skipping link database: %s", label)
            return []

        # Must have sent and concept at minimum
        if "concept" not in tables or "sent" not in tables:
            logger.debug("Skipping (no concept/sent): %s", label)
            return []

        lang = _extract_lang(con, db_path)

        if "doc" in tables:
            doc_stats = _stats_with_doc_table(con, tables)
        elif "subcorp" in tables:
            doc_stats = _stats_with_subcorp(con, tables)
        else:
            doc_name = _derive_doc_name(db_path)
            doc_stats = _stats_single_doc(con, tables, doc_name)

        return [(lang, doc, label, stats) for doc, stats in doc_stats.items()]

    except sqlite3.OperationalError as exc:
        logger.warning("Error scanning %s: %s", label, exc)
        return []
    finally:
        con.close()


def find_databases() -> tuple[list[Path], list[Path]]:
    """Locate build and old databases.

    Returns:
        Tuple of (build_db_paths, old_db_paths).
    """
    build_dbs: list[Path] = []
    for lang in BUILD_LANGS:
        p = BUILD_DIR / f"{lang}.db"
        if p.exists():
            build_dbs.append(p)
        else:
            logger.warning("Build DB not found: %s", p)

    old_dbs: list[Path] = []
    if OLD_ROOT.exists():
        for p in sorted(OLD_ROOT.rglob("*.db")):
            stem = p.stem.lower()
            # Skip WordNet databases
            if "wn" in stem:
                continue
            old_dbs.append(p)
    else:
        logger.warning("Old DB directory not found: %s", OLD_ROOT)

    return build_dbs, old_dbs


def main() -> None:
    """Scan all databases and print a comparison report to stdout."""
    build_dbs, old_dbs = find_databases()
    logger.info("Found %d build DBs, %d old DBs", len(build_dbs), len(old_dbs))

    # Collect build stats: (lang, doc) -> DocStats
    build_stats: dict[tuple[str, str], DocStats] = {}
    for db_path in build_dbs:
        logger.info("Scanning build: %s", db_path.name)
        for lang, doc, _label, stats in scan_database(db_path):
            build_stats[(lang, doc)] = stats

    logger.info("Build: %d (lang, doc) entries", len(build_stats))

    # Collect old stats: (lang, doc) -> list of (db_label, DocStats)
    old_stats: dict[tuple[str, str], list[SourceRecord]] = {}
    for db_path in old_dbs:
        logger.info("Scanning old: %s", _relative_label(db_path))
        for lang, doc, label, stats in scan_database(db_path):
            key = (lang, doc)
            old_stats.setdefault(key, []).append(SourceRecord(label, stats))

    logger.info("Old: %d (lang, doc) entries", len(old_stats))

    # Build the comparison report.
    # For each (lang, doc) seen in either build or old, find the best old
    # version and compare.
    all_keys = sorted(set(build_stats.keys()) | set(old_stats.keys()))

    # Header
    header = "\t".join([
        "doc",
        "lang",
        "build_sents",
        "build_words",
        "build_concepts",
        "build_distinct",
        "best_other_concepts",
        "best_other_db",
        "status",
    ])
    print(header)

    n_fewer = 0
    n_missing = 0
    for lang, doc in all_keys:
        b = build_stats.get((lang, doc))
        b_concepts = b.tagged_concepts if b else 0
        b_sents = b.sentences if b else 0
        b_words = b.words if b else 0
        b_distinct = b.distinct_tags if b else 0

        # Find the old version with the most tagged concepts
        others = old_stats.get((lang, doc), [])
        if others:
            best = max(others, key=lambda r: r.stats.tagged_concepts)
            best_concepts = best.stats.tagged_concepts
            best_db = best.db_path
        else:
            best_concepts = 0
            best_db = ""

        if b_concepts == 0 and best_concepts > 0:
            status = "MISSING"
            n_missing += 1
        elif b_concepts < best_concepts:
            status = "FEWER"
            n_fewer += 1
        else:
            status = "OK"

        row = "\t".join([
            doc,
            lang,
            str(b_sents),
            str(b_words),
            str(b_concepts),
            str(b_distinct),
            str(best_concepts),
            best_db,
            status,
        ])
        print(row)

    logger.info(
        "Summary: %d OK, %d FEWER, %d MISSING out of %d entries",
        len(all_keys) - n_fewer - n_missing,
        n_fewer,
        n_missing,
        len(all_keys),
    )


if __name__ == "__main__":
    main()
