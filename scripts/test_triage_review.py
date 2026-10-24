"""Tests for triage_review.py on a tiny fixture."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import triage_review as t  # noqa: E402

HEAD = ["id", "synset", "word", "other_words_in_synset", "english_words",
        "english_definition", "own_definition"]


def make_triage(root: Path) -> None:
    """Three cmn senses, two flagged by triage; empty id/zsm."""
    for lang in t.LANGS:
        (root / lang).mkdir(parents=True)
    t.write_tsv(root / "cmn" / "batch001.tsv", HEAD,
                [[f"cmn001-{i}", f"cow-0000000{i}-n", w, "", "x", "def", ""]
                 for i, w in enumerate(["猫", "狗", "鱼"], 1)])
    t.write_tsv(root / "cmn" / "batch001-suspects.tsv", ["id", "word", "reason"],
                [["cmn001-1", "猫", "odd"], ["cmn001-3", "鱼", "odd"]])


def review(out: Path, run: int, verdict: dict, note: dict | None = None) -> None:
    """Write run<run> reviews of the cmn batches with the given verdicts by word."""
    d = out / "cmn" / f"run{run}"
    rows = [[r["id"], r["word"], verdict[r["word"]], "why", (note or {}).get(r["word"], "")]
            for f in sorted(d.glob("batch[0-9][0-9][0-9].tsv")) for r in t.read_tsv(f)]
    t.write_tsv(d / "batch001-review.tsv", ["id", "word", "verdict", "reason", "note"], rows)


def test_build_compare_final(tmp_path: Path) -> None:
    # Arrange
    tri, out = tmp_path / "triage", tmp_path / "opus"
    make_triage(tri)
    t.build(tri, out, 150, 1)
    review(out, 1, {"猫": "OK", "鱼": "WRONG"}, {"鱼": "FORM"})
    review(out, 2, {"猫": "WRONG", "鱼": "WRONG"}, {"鱼": "FORM"})

    # Act
    t.compare(tri, out, 100, 1)
    adj = t.read_tsv(out / "cmn" / "adjudicate" / "batch001.tsv")
    t.write_tsv(out / "cmn" / "adjudicate" / "batch001-review.tsv",
                ["id", "word", "verdict", "reason"], [[adj[0]["id"], "猫", "OK", "fine"]])
    t.final(tri, out)

    # Assert
    assert [r["word"] for r in adj] == ["猫"]
    fin = {r["word"]: r for r in t.read_tsv(out / "cmn" / "final.tsv")}
    assert set(fin) == {"猫", "鱼"}
    assert (fin["猫"]["action"], fin["猫"]["decided_by"]) == ("keep", "adjudication")
    assert (fin["鱼"]["action"], fin["鱼"]["note_both"]) == ("remove", "FORM")
