"""Tests for def_review.py."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import def_review as dr
import triage_review as tr


def run(d: Path, rows: list[list[str]]) -> None:
    """Write one review run: key.tsv and batch001-review.tsv."""
    d.mkdir(parents=True)
    tr.write_tsv(d / "key.tsv", ["id", "synset"], [[r[0], r[1]] for r in rows])
    tr.write_tsv(d / "batch001-review.tsv", ["id", "verdict", "reason", "suggestion"],
                 [[r[0], *r[2:]] for r in rows])


def test_settled_needs_same_definite_verdict() -> None:
    assert dr.settled(("OK", "", ""), ("OK", "x", ""))
    assert dr.settled(("PARTIAL", "", "a"), ("PARTIAL", "", "b"))
    assert not dr.settled(("OK", "", ""), ("PARTIAL", "", ""))
    assert not dr.settled(("UNSURE", "", ""), ("UNSURE", "", ""))


def test_final_uses_agreement_then_adjudication(tmp_path: Path) -> None:
    # Arrange
    tr.write_tsv(tmp_path / "definitions.tsv", ["synset", *dr.COLS],
                 [["s1", "", "", "", "d1"], ["s2", "", "", "", "d2"], ["s3", "", "", "", "d3"]])
    run(tmp_path / "run1", [["1", "s1", "wrong", "no", "baru"], ["2", "s2", "OK", "", ""],
                            ["3", "s3", "OK", "", ""]])
    run(tmp_path / "run2", [["7", "s1", "WRONG", "", "lain"], ["8", "s2", "PARTIAL", "x", "y"],
                            ["9", "s3", "UNSURE", "?", ""]])
    run(tmp_path / "adjudicate", [["5", "s2", "PARTIAL", "short", "lebih"]])
    # Act
    dr.final(argparse.Namespace(out=tmp_path))
    # Assert
    got = [(r["synset"], r["final"], r["decided_by"], r["suggestion"])
           for r in tr.read_tsv(tmp_path / "final.tsv")]
    assert got == [("s1", "WRONG", "both", "baru"), ("s2", "PARTIAL", "adjudication", "lebih"),
                   ("s3", "UNSURE", "none", "")]
