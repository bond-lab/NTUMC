"""Tests for bahasa_rescue.py."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bahasa_rescue as br
import triage_review as tr


def corrections(path: Path, rows: list[list[str]]) -> Path:
    """Write a corrections file with the given rows."""
    tr.write_tsv(path, tr.CORR_HEAD, rows)
    return path


def test_tab_candidates_skips_x_decided_and_other_languages(tmp_path: Path) -> None:
    # Arrange
    tab = tmp_path / "wn-msa-all.tab"
    lines = [
        "00001-n\tI\tL\tkata",
        "00001-n\tB\tM\tkata",      # best status wins
        "00001-n\tI\tO\tsalah",
        "00001-n\tB\tX\tsalah",     # hand-checked bad anywhere: dropped
        "00001-n\tI\tO\tdibuang",   # removed by the review: dropped
        "00001-n\tM\tO\tmelayu",    # Malay only
        "00001-n\tI\tY\tbaik",      # Y is already in the release
        "00002-n\tI\tO\tlain",      # not a wordless synset
    ]
    tab.write_text("\n".join(lines) + "\n", encoding="utf-8")
    corr = corrections(tmp_path / "senses.tsv",
                       [["wnb-id-00001-n", "dibuang", "remove", "", "", "", "", ""]])
    # Act
    cand = br.tab_candidates(tab, {"wnb-id-00001-n"}, corr)
    # Assert
    assert cand == {"wnb-id-00001-n": {"kata": "M"}}


def test_proposals_split_words(tmp_path: Path) -> None:
    # Arrange
    tr.write_tsv(tmp_path / "batch001.tsv", br.GEN_HEAD,
                 [["g1", "wnb-id-00001-n", "", "", ""], ["g2", "wnb-id-00002-n", "", "", ""]])
    tr.write_tsv(tmp_path / "batch001-words.tsv", ["id", "words", "definition", "note"],
                 [["g1", "kucing; meong ", "OK", ""], ["g2", "", "WRONG", "no word"]])
    # Act
    got = br.proposals(tmp_path)
    # Assert
    assert got == {"wnb-id-00001-n": {"kucing", "meong"}}


def test_adds_keep_ok_without_form_notes(tmp_path: Path) -> None:
    # Arrange
    corr = corrections(tmp_path / "senses.tsv",
                       [["wnb-id-00009-n", "x", "remove", "", "r", "triage", "d", ""]])
    (tmp_path / "review" / "id").mkdir(parents=True)
    head = ["synset", "word", "haiku_reason", "run1", "run2", "final", "action",
            "decided_by", "reason", "note_both", "note_one"]
    tr.write_tsv(tmp_path / "review" / "id" / "final.tsv", head, [
        ["wnb-id-00001-n", "kucing", "", "OK", "OK", "OK", "keep", "both", "cat", "", ""],
        ["wnb-id-00001-n", "pensel", "", "OK", "OK", "OK", "keep", "both", "", "MS", ""],
        ["wnb-id-00001-n", "meong", "", "OK", "OK", "OK", "keep", "both", "", "", ""],
        ["wnb-id-00002-n", "salah", "", "OK", "WRONG", "WRONG", "remove",
         "adjudication", "no", "", ""],
    ])
    tr.write_tsv(tmp_path / "sources.tsv", ["synset", "word", "source"], [
        ["wnb-id-00001-n", "kucing", "tab O"], ["wnb-id-00001-n", "pensel", "tab L"],
        ["wnb-id-00001-n", "meong", "proposed"],
        ["wnb-id-00002-n", "salah", "tab O"]])
    a = argparse.Namespace(review=tmp_path / "review", out=tmp_path, corrections=corr,
                           date="2026-10-24")
    # Act
    br.adds(a)
    # Assert
    rows = tr.read_tsv(corr)
    assert [(r["lemma"], r["action"], r["reason"], r["source"]) for r in rows] == [
        ("x", "remove", "r", "triage"),
        ("kucing", "add", "tab O: cat", "lemma rescue: 2 blind opus")]
    pending = tr.read_tsv(tmp_path / "proposed-pending.tsv")
    assert [(r["word"], r["review"]) for r in pending] == [("meong", "OK")]
