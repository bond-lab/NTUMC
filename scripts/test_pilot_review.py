"""Tests for pilot_review.py."""

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import pilot_review as pr
import triage_review as tr


@pytest.mark.parametrize("v1, v2, jm, want", [
    ("OK", "OK", False, "keep"),
    ("WRONG", "WRONG", True, "remove"),
    ("UNSURE", "OK", False, "lower"),
    ("UNSURE", "UNSURE", True, "lower"),
    ("UNSURE", "UNSURE", False, "queue"),
    ("OK", "WRONG", True, "queue"),
    ("WRONG", "UNSURE", True, "queue"),
    ("MISSING", "OK", True, "queue"),
])
def test_decide(v1: str, v2: str, jm: bool, want: str) -> None:
    # Act / Assert
    assert pr.decide(v1, v2, jm) == want
    assert pr.decide(v2, v1, jm) == want


def test_blind_writes_only_the_action(tmp_path: Path) -> None:
    # Arrange
    tr.write_tsv(tmp_path / "items.tsv", ["synset", *pr.COLS],
                 [[f"wnja-0000000{n}-n", w, *[""] * (len(pr.COLS) - 1)]
                  for n, w in enumerate(["犬", "猫", "鳥"])])
    tr.write_tsv(tmp_path / "final.tsv", ["synset", "word", "action"],
                 [["wnja-00000000-n", "犬", "remove"], ["wnja-00000001-n", "猫", "keep"],
                  ["wnja-00000002-n", "鳥", "remove"]])
    a = argparse.Namespace(out=tmp_path, action="remove", size=1)
    # Act
    pr.blind(a)
    # Assert
    d = tmp_path / "blind-remove"
    key = tr.read_tsv(d / "key.tsv")
    assert sorted(k["word"] for k in key) == ["犬", "鳥"]
    assert len(tr.read_tsv(d / "batch01.tsv")) == 1
    assert (d / "batch02.tsv").exists() and not (d / "batch03.tsv").exists()


def test_check_counts_wrong_share(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "key").mkdir()
    (tmp_path / "returned").mkdir()
    tr.write_tsv(tmp_path / "key" / "ja-pilot-key.tsv", ["item", "action"],
                 [["pc-001", "remove"], ["pc-002", "remove"], ["pc-003", "keep"]])
    tr.write_tsv(tmp_path / "returned" / "ja-pilot-sheet.tsv", ["item", "meaning"],
                 [["pc-001", "wrong"], ["pc-002", "OK"], ["pc-003", ""]])
    # Act
    pr.check(argparse.Namespace(sheet=tmp_path))
    # Assert
    rows = {r["action"]: r for r in tr.read_tsv(tmp_path / "key" / "score.tsv")}
    assert rows["remove"]["wrong_share"] == "0.50"
    assert rows["keep"]["blank"] == "1"
