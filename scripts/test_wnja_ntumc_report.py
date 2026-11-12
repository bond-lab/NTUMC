"""Tests for wnja_ntumc_report.py."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import wnja_ntumc_report as wr


def test_spellings_of_suru_verb() -> None:
    # Act
    got = wr.spellings_of("区分+する")
    # Assert
    assert {"区分する", "区分"} <= got


def test_norm_drops_multiword_joins() -> None:
    # Act / Assert
    assert wr.norm("オープン_ソース") == "オープンソース"
    assert wr.norm("何 か") == "何か"


def test_ntumc_defs_joins_parts(tmp_path: Path) -> None:
    # Arrange
    db = tmp_path / "wn.db"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE synset_def (synset TEXT, lang TEXT, def TEXT, sid INTEGER)")
        con.executemany("INSERT INTO synset_def VALUES (?, ?, ?, ?)",
                        [("1-n", "jpn", "後", 1), ("1-n", "jpn", "前", 0),
                         ("1-n", "eng", "x", 0)])
    # Act
    got = wr.ntumc_defs(db)
    # Assert
    assert got["1-n"] == {"前", "後", "前; 後"}
