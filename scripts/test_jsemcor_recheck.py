"""Tests for jsemcor_recheck.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import jsemcor_recheck as jr
import triage_review as tr


def test_rejected_skips_added_and_checked(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "corrections").mkdir()
    (tmp_path / "audit" / "reviews" / "jsemcor").mkdir(parents=True)
    tr.write_tsv(tmp_path / "corrections" / "senses.tsv",
                 ["synset_id", "lemma", "action", "confidence", "reason", "source", "date",
                  "new_lemma"],
                 [["wnja-00000003-n", "犬", "add", "0.8", "", "jsemcor review", "", ""]])
    head = ["synset", "lemma", "run1", "run2", "final", "decided_by", "reason"]
    tr.write_tsv(tmp_path / "audit" / "reviews" / "jsemcor" / "verdicts.tsv", head, [
        ["00000001-n", "猫", "WRONG", "WRONG", "WRONG", "all runs", "no"],
        ["00000002-n", "鳥", "ADD", "ADD", "ADD", "all runs", ""],
        ["00000003-n", "犬", "WRONG", "ADD", "WRONG", "adjudicated", "added later"],
        ["00000004-n", "魚", "MWE", "MWE", "MWE", "all runs", ""],
        ["00000005-n", "馬", "WRONG", "WRONG", "WRONG", "all runs", "checked"],
    ])
    # Act
    got = jr.rejected(tmp_path, {("00000005-n", "馬")})
    # Assert
    assert [(r["synset"], r["lemma"]) for r in got] == [("00000001-n", "猫"), ("00000004-n", "魚")]
