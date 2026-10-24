"""Tests for spot_check.py."""

import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import spot_check as sc
import triage_review as tr


def test_stratum_of_corrections_rows() -> None:
    row = lambda action, source: {"action": action, "source": source}
    assert sc.stratum(row("remove", "triage: haiku + 2 blind opus")) == "remove-wrong"
    assert sc.stratum(row("remove", "triage: haiku + 2 blind opus (adjudicated)")) \
        == "remove-wrong-adj"
    assert sc.stratum(row("remove", "triage: haiku + 2 blind opus + form note")) == "remove-form"
    assert sc.stratum(row("rename", "form: mechanical")) == "rename-mechanical"
    assert sc.stratum(row("add", "rescue: 2 blind opus")) == "rescue"
    assert sc.stratum(row("add", "triage: haiku + 2 blind opus + form note")) == "move"


def test_agrees() -> None:
    assert sc.agrees("remove-wrong", "wrong", "") is True
    assert sc.agrees("remove-wrong", "OK", "") is False
    assert sc.agrees("remove-form", "OK", "Malaysian only") is True
    assert sc.agrees("remove-form", "OK", "OK") is False
    assert sc.agrees("keep", "OK", "") is True
    assert sc.agrees("keep", "OK", "malformed") is False
    assert sc.agrees("keep", "", "") is None
    assert sc.agrees("lower", "OK", "") is None


def test_wilson() -> None:
    lo, hi = sc.wilson(20, 20)
    assert round(lo, 2) == 0.84 and hi == 1.0
    assert sc.wilson(0, 0) == (0.0, 1.0)


def test_score_writes_agreement(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "key").mkdir()
    tr.write_tsv(tmp_path / "key" / "strata.tsv", ["lang", "stratum", "population", "sample"],
                 [["cmn", "keep", 100, 2], ["cmn", "lower", 10, 1]])
    tr.write_tsv(tmp_path / "key" / "cmn-key.tsv", sc.KEY,
                 [["cmn-001", "keep", "s1", "猫", "", "keep", "both", ""],
                  ["cmn-002", "keep", "s2", "狗", "", "keep", "both", ""],
                  ["cmn-003", "lower", "s3", "鱼", "", "lower", "adjudication", ""]])
    tr.write_tsv(tmp_path / "cmn-sheet.tsv", sc.SHEET,
                 [["cmn-001", "猫", "", "", "", "", "OK", "", ""],
                  ["cmn-002", "狗", "", "", "", "", "WRONG", "", ""],
                  ["cmn-003", "鱼", "", "", "", "", "unsure", "", ""]])

    # Act
    sc.score(Namespace(out=tmp_path))

    # Assert
    got = {r["stratum"]: r for r in tr.read_tsv(tmp_path / "key" / "score.tsv")}
    assert (got["keep"]["checked"], got["keep"]["agreement"]) == ("2", "0.50")
    assert got["lower"]["agreement"] == "UNSURE:1"
