"""Tests for fix_cpos.py: word character offsets."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_cpos import Options, find_word_offsets, process_db, sentence_updates

ROOT = Path(__file__).resolve().parents[1]


def test_find_word_offsets_plain() -> None:
    assert find_word_offsets("The cat sat.", ["The", "cat", "sat", "."]) == [
        (0, 3),
        (4, 7),
        (8, 11),
        (11, 12),
    ]


def test_find_word_offsets_missing_word_does_not_advance() -> None:
    assert find_word_offsets("a b", ["a", "x", "b"]) == [(0, 1), None, (2, 3)]


def test_find_word_offsets_max_gap() -> None:
    text = "a long way b"
    assert find_word_offsets(text, ["a", "b"]) == [(0, 1), (11, 12)]
    assert find_word_offsets(text, ["a", "b"], max_gap=3) == [(0, 1), None]


def test_sentence_updates_only_changed_rows() -> None:
    words = [(0, "a", 0, 1), (1, "b", 9, 10), (2, "c", None, None)]
    assert sentence_updates("a b c", words, Options()) == ([(2, 3, 1), (4, 5, 2)], 0)


def test_sentence_updates_strict_skips_sentence() -> None:
    words = [(0, "a", 0, 1), (1, "x", 9, 10)]
    assert sentence_updates("a b", words, Options(mismatched=True)) == ([], 1)
    assert sentence_updates("a b", words, Options()) == ([], 1)


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """Three sentences: no offsets, drifted offsets, and a bad tokenisation."""
    path = tmp_path / "jpn.db"
    conn = sqlite3.connect(path)
    conn.executescript((ROOT / "data" / "ntumc.sql").read_text())
    conn.execute(
        "INSERT INTO corpus (corpusID, corpus, title, language, genre) "
        "VALUES (1, 'story', 'S', 'jpn', 'fiction')"
    )
    conn.execute(
        "INSERT INTO doc (docid, doc, title, corpusID) VALUES (1, 'd', 'D', 1)"
    )
    conn.executemany(
        "INSERT INTO sent (sid, docID, sent) VALUES (?, 1, ?)",
        [(1, "極楽の蓮"), (2, "しかし極楽の蓮"), (3, "ab cd")],
    )
    conn.executemany(
        "INSERT INTO word (sid, wid, word, cfrom, cto) VALUES (?, ?, ?, ?, ?)",
        [
            (1, 0, "極楽", None, None),
            (1, 1, "の", "", ""),
            (1, 2, "蓮", None, None),
            (2, 0, "しかし", 0, 3),
            (2, 1, "極楽", 3, 5),
            (2, 2, "の", 6, 7),
            (2, 3, "蓮", 6, "頓着"),
            (3, 0, "ab", 0, 2),
            (3, 1, "xx", 3, 5),
        ],
    )
    conn.commit()
    conn.close()
    return path


def _offsets(path: Path, sid: int) -> list[tuple]:
    conn = sqlite3.connect(path)
    return conn.execute(
        "SELECT cfrom, cto FROM word WHERE sid = ? ORDER BY wid", (sid,)
    ).fetchall()


def test_populate_fills_only_empty_sentences(db: Path) -> None:
    counts = process_db(str(db), Options())
    assert (counts.sentences, counts.updated) == (1, 3)
    assert _offsets(db, 1) == [(0, 2), (2, 3), (3, 4)]
    assert _offsets(db, 2)[2] == (6, 7)


def test_mismatched_repairs_drifted_and_skips_unmatchable(db: Path) -> None:
    counts = process_db(str(db), Options(mismatched=True, max_gap=3))
    assert (counts.sentences, counts.updated, counts.failed) == (2, 2, 1)
    assert _offsets(db, 2) == [(0, 3), (3, 5), (5, 6), (6, 7)]
    assert _offsets(db, 3) == [(0, 2), (3, 5)]
    assert _offsets(db, 1) == [(None, None), ("", ""), (None, None)]


def test_mismatched_is_logged(db: Path) -> None:
    process_db(str(db), Options(mismatched=True, max_gap=3))
    conn = sqlite3.connect(db)
    assert conn.execute(
        "SELECT cto_old, cto_new FROM word_log WHERE sid_old = 2 AND wid_old = 3"
    ).fetchall() == [("頓着", 7)]


def test_dry_run_writes_nothing(db: Path) -> None:
    counts = process_db(str(db), Options(mismatched=True, max_gap=3, dry_run=True))
    assert counts.updated == 2
    assert _offsets(db, 2)[3] == (6, "頓着")
