"""Tests for check_links.py: link rows whose ends are missing."""

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_links import check, corpus_names, delete_dangling, find_dangling

ROOT = Path(__file__).resolve().parents[1]


def _corpus(path: Path, sents: dict[int, str]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript((ROOT / "data" / "ntumc.sql").read_text())
    conn.execute(
        "INSERT INTO corpus (corpusID, corpus, title, language, genre) "
        "VALUES (1, 'story', 'S', 'xx', 'fiction')"
    )
    conn.execute(
        "INSERT INTO doc (docid, doc, title, corpusID) VALUES (1, 'd', 'D', 1)"
    )
    for sid, text in sents.items():
        conn.execute(
            "INSERT INTO sent (sid, docID, sent) VALUES (?, 1, ?)", (sid, text)
        )
        for wid, word in enumerate(text.split()):
            conn.execute(
                "INSERT INTO word (sid, wid, word) VALUES (?, ?, ?)", (sid, wid, word)
            )
            conn.execute(
                "INSERT INTO concept (sid, cid, clemma) VALUES (?, ?, ?)",
                (sid, wid, word),
            )
    conn.commit()
    conn.close()


@pytest.fixture
def build(tmp_path: Path) -> Path:
    """eng.db, xxx.db and eng-xxx.db with one dangling row per link table."""
    _corpus(tmp_path / "eng.db", {1: "a b", 2: "c"})
    _corpus(tmp_path / "xxx.db", {1: "x y", 2: "z"})
    conn = sqlite3.connect(tmp_path / "eng-xxx.db")
    conn.executescript((ROOT / "data" / "link.sql").read_text())
    conn.execute(
        "INSERT INTO meta (fcorpus, flang, tcorpus, tlang) "
        "VALUES ('eng.db', 'eng', 'xxx.db', 'xxx')"
    )
    conn.executemany(
        "INSERT INTO slink (fsid, tsid) VALUES (?, ?)", [(1, 1), (2, 2), (3, 2)]
    )
    conn.executemany(
        "INSERT INTO wlink (fsid, fwid, tsid, twid) VALUES (?, ?, ?, ?)",
        [(1, 0, 1, 1), (1, 1, 1, 5)],
    )
    conn.executemany(
        "INSERT INTO clink (fsid, fcid, tsid, tcid) VALUES (?, ?, ?, ?)",
        [(2, 0, 2, 0), (2, 7, 9, 0)],
    )
    conn.commit()
    conn.close()
    return tmp_path


def _attached(build: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(build / "eng-xxx.db")
    conn.execute("ATTACH ? AS f", (str(build / "eng.db"),))
    conn.execute("ATTACH ? AS t", (str(build / "xxx.db"),))
    return conn


def test_corpus_names(build: Path) -> None:
    link = build / "eng-xxx.db"
    conn = sqlite3.connect(link)
    assert corpus_names(conn, link) == ("eng.db", "xxx.db")
    conn.execute("DELETE FROM meta")
    assert corpus_names(conn, link) == ("eng.db", "xxx.db")
    with pytest.raises(ValueError):
        corpus_names(conn, build / "links.db")


def test_find_dangling(build: Path) -> None:
    conn = _attached(build)
    slinks = find_dangling(conn, "slink")
    assert [(r.from_ids, r.to_ids, r.missing) for r in slinks] == [((3,), (2,), "from")]
    wlinks = find_dangling(conn, "wlink")
    assert [(r.from_ids, r.to_ids, r.missing) for r in wlinks] == [
        ((1, 1), (1, 5), "to")
    ]
    clinks = find_dangling(conn, "clink")
    assert [(r.from_ids, r.to_ids, r.missing) for r in clinks] == [
        ((2, 7), (9, 0), "both")
    ]


def test_delete_dangling(build: Path) -> None:
    conn = _attached(build)
    rows = find_dangling(conn, "slink")
    with conn:
        assert delete_dangling(conn, rows) == 1
    assert conn.execute("SELECT fsid, tsid FROM slink ORDER BY fsid").fetchall() == [
        (1, 1),
        (2, 2),
    ]
    assert conn.execute(
        "SELECT fsid_old FROM slink_log WHERE tsid_old = 2 AND fsid_old = 3"
    ).fetchall()
    assert find_dangling(conn, "slink") == []


def test_check_reports_then_fixes(build: Path) -> None:
    assert check(build / "eng-xxx.db", None, fix=False) == 3
    assert check(build / "eng-xxx.db", None, fix=True) == 3
    assert check(build / "eng-xxx.db", None, fix=False) == 0
    conn = sqlite3.connect(build / "eng-xxx.db")
    assert conn.execute("SELECT COUNT(*) FROM clink").fetchone() == (1,)
