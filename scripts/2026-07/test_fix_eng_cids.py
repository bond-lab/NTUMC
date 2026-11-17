"""Tests for fix_eng_cids.py: 0-based concept ids per sentence."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_eng_cids import find_cids_to_fix, link_resolution, renumber

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def eng_db(tmp_path: Path) -> Path:
    """A corpus database with document-wide cids in sentences 2 and 3."""
    path = tmp_path / "eng.db"
    conn = sqlite3.connect(path)
    conn.executescript((ROOT / "data" / "ntumc.sql").read_text())
    conn.execute(
        "INSERT INTO corpus (corpusID, corpus, title, language, genre) "
        "VALUES (1, 'essay', 'Essays', 'eng', 'essay')"
    )
    conn.execute(
        "INSERT INTO doc (docid, doc, title, corpusID) VALUES (1, 'catb', 'T', 1)"
    )
    conn.executemany(
        "INSERT INTO sent (sid, docID, sent) VALUES (?, 1, ?)",
        [(1, "a b"), (2, "c d e"), (3, "f")],
    )
    # sentence 1 is already 0-based; 2 and 3 continue the document count
    concepts = [
        (1, 0, "a"),
        (1, 1, "b"),
        (2, 2, "c"),
        (2, 3, "d"),
        (2, 10, "e"),
        (3, 11, "f"),
    ]
    conn.executemany(
        "INSERT INTO concept (sid, cid, clemma, tag) VALUES (?, ?, ?, 'x')",
        concepts,
    )
    conn.executemany(
        "INSERT INTO cwl (sid, cid, wid) VALUES (?, ?, ?)",
        [(s, c, i) for i, (s, c, _) in enumerate(concepts)],
    )
    conn.execute("INSERT INTO sentiment (sid, cid, score) VALUES (2, 10, 50)")
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def link_db(tmp_path: Path) -> Path:
    """An eng-xxx link database whose clinks use 0-based English cids."""
    path = tmp_path / "eng-xxx.db"
    conn = sqlite3.connect(path)
    conn.executescript((ROOT / "data" / "link.sql").read_text())
    conn.execute(
        "INSERT INTO meta (fcorpus, flang, tcorpus, tlang) "
        "VALUES ('eng.db', 'eng', 'xxx.db', 'xxx')"
    )
    conn.executemany(
        "INSERT INTO clink (fsid, fcid, tsid, tcid, ltype) VALUES (?, ?, ?, ?, '=')",
        [(1, 1, 1, 0), (2, 0, 2, 0), (2, 2, 2, 1), (3, 0, 3, 0)],
    )
    conn.commit()
    conn.close()
    return path


def test_find_cids_to_fix(eng_db: Path) -> None:
    conn = sqlite3.connect(eng_db)
    assert find_cids_to_fix(conn) == {2: [2, 3, 10], 3: [11]}


def test_renumber_updates_every_table(eng_db: Path) -> None:
    conn = sqlite3.connect(eng_db)
    counts = renumber(conn, find_cids_to_fix(conn))
    conn.commit()
    assert counts == {"concept": 4, "cwl": 4, "sentiment": 1}
    rows = conn.execute(
        "SELECT sid, cid, clemma FROM concept ORDER BY sid, cid"
    ).fetchall()
    assert rows == [
        (1, 0, "a"),
        (1, 1, "b"),
        (2, 0, "c"),
        (2, 1, "d"),
        (2, 2, "e"),
        (3, 0, "f"),
    ]
    assert conn.execute(
        "SELECT sid, cid, wid FROM cwl WHERE sid = 2 ORDER BY cid"
    ).fetchall() == [
        (2, 0, 2),
        (2, 1, 3),
        (2, 2, 4),
    ]
    assert conn.execute("SELECT cid FROM sentiment").fetchall() == [(2,)]
    assert find_cids_to_fix(conn) == {}


def test_renumber_is_logged(eng_db: Path) -> None:
    conn = sqlite3.connect(eng_db)
    before = conn.execute("SELECT COUNT(*) FROM concept_log").fetchone()[0]
    renumber(conn, find_cids_to_fix(conn))
    logged = conn.execute(
        "SELECT cid_old, cid_new FROM concept_log WHERE sid_old = 2 "
        "AND cid_old IS NOT NULL AND cid_new IS NOT NULL ORDER BY cid_old"
    ).fetchall()
    assert logged == [(2, 0), (3, 1), (10, 2)]
    assert conn.execute("SELECT COUNT(*) FROM concept_log").fetchone()[0] == before + 4


def test_links_resolve_after_renumbering(eng_db: Path, link_db: Path) -> None:
    # (1, 1) exists; (2, 2) exists too but is the wrong concept, as in catb
    assert link_resolution(link_db, eng_db) == (2, 4)
    conn = sqlite3.connect(eng_db)
    with conn:
        renumber(conn, find_cids_to_fix(conn))
    conn.close()
    assert link_resolution(link_db, eng_db) == (4, 4)
