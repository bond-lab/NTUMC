"""Tests for change records (ntumc.wordnet.changes)."""

from pathlib import Path

import pytest

from ntumc.wordnet import changes, lmf
from ntumc.wordnet.__main__ import apply
from ntumc.wordnet.changes import Change
from ntumc.wordnet.model import Entry, Item, Synset

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE LexicalResource SYSTEM "https://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd">
<LexicalResource xmlns:dc="https://globalwordnet.github.io/schemas/dc/">
  <Lexicon id="tst" label="Test" language="ja" email="a@example.org" license="x" version="1">
    <LexicalEntry id="tst-n-0">
      <Lemma writtenForm="犬" partOfSpeech="n" />
      <Form writtenForm="いぬ" script="hira" />
      <Sense id="tst-1-n-0" synset="tst-1-n" />
      <Sense id="tst-2-n-0" synset="tst-2-n" confidenceScore="0.8" />
    </LexicalEntry>
    <LexicalEntry id="tst-n-1">
      <Lemma writtenForm="犬" partOfSpeech="n" />
      <Form writtenForm="けん" script="hira" />
      <Sense id="tst-3-n-1" synset="tst-3-n" />
    </LexicalEntry>
    <LexicalEntry id="tst-n-2">
      <Lemma writtenForm="狗" partOfSpeech="n" />
      <Form writtenForm="いぬ" script="hira" />
      <Sense id="tst-1-n-2" synset="tst-1-n" />
    </LexicalEntry>
    <LexicalEntry id="tst-n-3">
      <Lemma writtenForm="ワンワン" partOfSpeech="n" />
      <Sense id="tst-1-n-3" synset="tst-1-n" />
    </LexicalEntry>
    <Synset id="tst-1-n" ili="i1" partOfSpeech="n"
            members="tst-1-n-0 tst-1-n-2 tst-1-n-3">
      <Definition>a canine</Definition>
      <SynsetRelation relType="hypernym" target="tst-2-n" />
    </Synset>
    <Synset id="tst-2-n" ili="i2" partOfSpeech="n" members="tst-2-n-0">
      <SynsetRelation relType="hyponym" target="tst-1-n" />
    </Synset>
    <Synset id="tst-3-n" ili="i3" partOfSpeech="n" members="tst-3-n-1">
      <SynsetRelation relType="hypernym" target="tst-2-n" />
      <SynsetRelation relType="similar" target="tst-1-n" />
    </Synset>
  </Lexicon>
</LexicalResource>
"""


@pytest.fixture
def base(tmp_path: Path) -> Path:
    path = tmp_path / "base.xml"
    path.write_text(XML, encoding="utf-8")
    return path


def change(action: str, n: int = 1, **kw: str) -> Change:
    return Change(id=f"c{n}", action=action, lexicon="tst", user="ann",
                  source="native check", reason="test", **kw)


def run(base: Path, *cs: Change) -> tuple[list[Item], list[str]]:
    return changes.apply(lmf.read(base), cs)


def entries(items: list[Item]) -> dict[str, Entry]:
    return {str(i.id): i for i in items if isinstance(i, Entry)}


def synsets(items: list[Item]) -> dict[str, Synset]:
    return {str(i.id): i for i in items if isinstance(i, Synset)}


def test_remove_sense_drops_the_empty_entry_and_the_member(base: Path) -> None:
    # Act
    items, conflicts = run(base, change("remove_sense", synset="tst-1-n", lemma="ワンワン"))
    # Assert
    assert conflicts == []
    assert "tst-n-3" not in entries(items)
    assert synsets(items)["tst-1-n"].members == "tst-1-n-0 tst-1-n-2"


def test_set_confidence_checks_the_old_value(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("set_confidence", 1, synset="tst-2-n", lemma="犬", old="0.8", new="0.5"),
        change("set_confidence", 2, synset="tst-1-n", lemma="犬", old="0.9", new="0.5"))
    # Assert
    senses = {s.id: s for s in entries(items)["tst-n-0"].senses}
    assert senses["tst-2-n-0"].meta["confidenceScore"] == "0.5"
    assert "confidenceScore" not in senses["tst-1-n-0"].meta
    assert conflicts == ["c2: set_confidence: confidence of 犬 in tst-1-n is not 0.9"]


def test_add_sense_makes_an_entry_with_ids_like_the_others(base: Path) -> None:
    # Act
    items, conflicts = run(base, change("add_sense", synset="tst-2-n", lemma="動物"))
    # Assert
    assert conflicts == []
    new = entries(items)["tst-n-4"]
    assert (new.lemma, new.pos, new.senses[0].id) == ("動物", "n", "tst-2-n-4")
    assert synsets(items)["tst-2-n"].members == "tst-2-n-0 tst-2-n-4"


def test_add_sense_needs_a_reading_for_a_homograph(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("add_sense", 1, synset="tst-2-n", lemma="犬"),
        change("add_sense", 2, synset="tst-3-n", lemma="犬", reading="いぬ"),
        change("add_sense", 3, synset="tst-3-n", lemma="犬", reading="けん"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c1", "c3"]  # exists; exists
    assert "tst-3-n-0" in {s.id for s in entries(items)["tst-n-0"].senses}


def test_rename_moves_the_sense_to_an_entry_with_the_same_reading(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("rename_lemma", 1, synset="tst-2-n", lemma="犬", new="狗"),
        change("rename_lemma", 2, synset="tst-1-n", lemma="ワンワン", new="わんわん"))
    # Assert
    assert conflicts == []
    got = entries(items)
    assert {s.synset for s in got["tst-n-2"].senses} == {"tst-1-n", "tst-2-n"}
    assert got["tst-n-3"].lemma == "わんわん"  # no other sense: renamed in place


def test_add_form_and_texts(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("add_form", 1, lemma="犬", pos="n", reading="いぬ", new="イヌ", script="kana"),
        change("set_definition", 2, synset="tst-1-n", old="a canine", new="a dog"),
        change("set_definition", 3, synset="tst-1-n", old="a canine", new="a hound"),
        change("set_definition", 4, synset="tst-2-n", new="an animal"),
        change("add_example", 5, synset="tst-1-n", new="犬が吠えた", lang="ja"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c3"]
    assert [f.form for f in entries(items)["tst-n-0"].forms] == ["いぬ", "イヌ"]
    assert [f.form for f in entries(items)["tst-n-1"].forms] == ["けん"]
    got = synsets(items)
    assert got["tst-1-n"].definitions[0].text == "a dog"
    assert got["tst-2-n"].definitions[0].text == "an animal"
    assert got["tst-1-n"].examples[0].lang == "ja"


def test_relations_and_new_synset(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("add_synset", 1, synset="tst-9-n", pos="n", new="a young dog of any breed",
               ili="in", identifier="ntumc00001"),
        change("add_relation", 2, synset="tst-9-n", link="hypernym", target="tst-1-n"),
        change("add_relation", 3, synset="tst-9-n", link="hypernym", target="tst-1-n"),
        change("remove_relation", 4, synset="tst-3-n", link="similar", target="tst-1-n"),
        change("add_sense", 5, synset="tst-9-n", lemma="子犬"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c3"]
    got = synsets(items)
    assert got["tst-9-n"].meta == {"dc:identifier": "ntumc00001"} and got["tst-9-n"].ili == "in"
    assert [(r.link, r.target) for r in got["tst-9-n"].relations] == [("hypernym", "tst-1-n")]
    assert [r.link for r in got["tst-3-n"].relations] == ["hypernym"]


def test_merge_synset_moves_senses_and_relations(base: Path) -> None:
    # Act
    items, conflicts = run(base, change("merge_synset", synset="tst-3-n", target="tst-1-n"))
    # Assert
    assert conflicts == []
    got = synsets(items)
    assert "tst-3-n" not in got
    assert entries(items)["tst-n-1"].senses[0].synset == "tst-1-n"
    assert got["tst-1-n"].members.split()[-1] == "tst-3-n-1"
    assert [(r.link, r.target) for r in got["tst-1-n"].relations] == [("hypernym", "tst-2-n")]


@pytest.mark.parametrize(("bad", "message"), [
    (Change(id="x", action="explode", lexicon="tst"), "unknown action"),
    (Change(id="x", action="remove_sense", lexicon="tst", synset="tst-1-n", lemma="犬",
            user="ann", reason="r"), "source is missing"),
    (Change(id="x", action="add_sense", lexicon="tst", synset="tst-1-n", lemma="猫",
            user="ann", reason="r", source="model: guess"), "model alone"),
    (Change(id="x", action="remove_sense", lexicon="other", synset="tst-1-n", lemma="犬",
            user="ann", reason="r", source="s"), "is for lexicon other"),
    (Change(id="x", action="remove_sense", lexicon="tst", synset="tst-1-n", lemma="猫",
            user="ann", reason="r", source="s"), "no sense of 猫"),
])
def test_bad_changes_are_conflicts_and_change_nothing(base: Path, bad: Change, message: str) -> None:
    # Act
    items, conflicts = run(base, bad)
    # Assert
    assert len(conflicts) == 1 and message in conflicts[0]
    assert items == list(lmf.read(base))


def test_records_round_trip_and_reject_unknown_fields(tmp_path: Path) -> None:
    # Arrange
    c = change("remove_sense", synset="tst-1-n", lemma="犬")
    # Act
    changes.write(tmp_path / "c.jsonl", [c])
    # Assert
    assert list(changes.read(tmp_path / "c.jsonl")) == [c]
    with pytest.raises(ValueError, match="colour"):
        changes.loads('{"id": "x", "colour": "red"}')


def test_apply_writes_nothing_when_there_is_a_conflict(base: Path, tmp_path: Path) -> None:
    # Arrange
    changes.write(tmp_path / "bad.jsonl", [change("remove_sense", synset="tst-1-n", lemma="猫")])
    changes.write(tmp_path / "good.jsonl", [change("remove_sense", synset="tst-1-n", lemma="狗")])
    # Act
    conflicts = apply(base, tmp_path / "bad.jsonl", tmp_path / "bad.xml")
    clean = apply(base, tmp_path / "good.jsonl", tmp_path / "good.xml", version="2")
    # Assert
    assert conflicts and not (tmp_path / "bad.xml").exists()
    assert clean == []
    new = list(lmf.read(tmp_path / "good.xml"))
    assert new[0].version == "2" and "tst-n-2" not in entries(new)
