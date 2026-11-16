"""Tests for change records (ntumc.wordnet.changes)."""

from pathlib import Path

import pytest

from ntumc.wordnet import changes, diff, lmf
from ntumc.wordnet.__main__ import apply
from ntumc.wordnet.__main__ import diff as diff_files
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


def test_remove_sense_can_name_one_sense_by_its_id(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("remove_sense", 1, synset="tst-1-n", lemma="ワンワン", sense="tst-9-n-9"),
        change("remove_sense", 2, synset="tst-1-n", lemma="ワンワン", sense="tst-1-n-3"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c1"]
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


def test_merge_synset_moves_relations_to_a_sense_it_drops(base: Path) -> None:
    # Act: 犬 is in both synsets, so its sense in tst-2-n is dropped
    items, conflicts = run(
        base,
        change("add_sense_relation", 1, synset="tst-1-n", lemma="ワンワン", link="similar",
               target="tst-2-n", target_lemma="犬"),
        change("merge_synset", 2, synset="tst-2-n", target="tst-1-n"))
    # Assert
    assert conflicts == []
    senses = {s.id: s for e in entries(items).values() for s in e.senses}
    assert "tst-2-n-0" not in senses
    assert [(r.link, r.target) for r in senses["tst-1-n-3"].relations] == [
        ("similar", "tst-1-n-0")]


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


def test_sense_relations_and_form_removal(base: Path) -> None:
    # Arrange
    link = {"synset": "tst-1-n", "lemma": "ワンワン", "link": "other", "target": "tst-2-n",
                "target_lemma": "犬", "subtype": "agent"}
    # Act
    items, conflicts = run(
        base,
        change("add_sense_relation", 1, **link),
        change("add_sense_relation", 2, **link),
        change("remove_form", 3, lemma="狗", pos="n", old="いぬ"),
        change("remove_form", 4, lemma="狗", pos="n", old="いぬ"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c4"]
    rel = entries(items)["tst-n-3"].senses[0].relations[0]
    assert (rel.link, rel.target, rel.meta) == ("other", "tst-2-n-0", {"dc:type": "agent"})
    assert entries(items)["tst-n-2"].forms == []
    again, conflicts = changes.apply(items, [change("remove_sense_relation", 5, **link)])
    assert conflicts == [] and entries(again)["tst-n-3"].senses[0].relations == []


NEW = (XML
       .replace('<Sense id="tst-1-n-3" synset="tst-1-n" />',
                '<Sense id="tst-2-n-3" synset="tst-2-n" confidenceScore="0.5" />')
       .replace('confidenceScore="0.8"', 'confidenceScore="0.6"')
       .replace("a canine", "a dog")
       .replace('<Form writtenForm="けん" script="hira" />',
                '<Form writtenForm="けん" script="hira" /><Form writtenForm="ケン" script="kana" />')
       .replace('<SynsetRelation relType="similar" target="tst-1-n" />',
                '<SynsetRelation relType="also" target="tst-1-n" /><Example>x y</Example>')
       .replace("</Lexicon>", '<Synset id="tst-9-n" ili="in" partOfSpeech="n" '
                'dc:identifier="ntumc00001"><Definition>a young dog</Definition></Synset>'
                "</Lexicon>"))


def test_diff_gives_records_that_rebuild_the_new_version(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    new.write_text(NEW, encoding="utf-8")
    # Act
    conflicts, left = diff_files(base, new, tmp_path / "c.jsonl", user="ann",
                                 source="rebuild", reason="test", base="tst-1")
    # Assert
    assert (conflicts, left) == ([], [])
    records = list(changes.read(tmp_path / "c.jsonl"))
    assert {r.action for r in records} == {
        "add_synset", "remove_sense", "add_sense", "set_confidence", "add_form",
        "set_definition", "add_example", "remove_relation", "add_relation"}
    assert all(r.lexicon == "tst" and r.base == "tst-1" for r in records)
    form = next(r for r in records if r.action == "add_form")
    assert (form.new, form.reading) == ("ケン", "けん")  # 犬 has two entries: which one


def test_diff_covers_counts(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    new.write_text(XML.replace('<Sense id="tst-1-n-3" synset="tst-1-n" />',
                               '<Sense id="tst-1-n-3" synset="tst-1-n">'
                               '<Count dc:source="x">3</Count></Sense>'), encoding="utf-8")
    # Act
    records = diff.diff(lmf.read(base), lmf.read(new), lexicon="tst", user="ann",
                        source="rebuild", reason="test")
    conflicts, extra, missing = diff.residual(lmf.read(base), lmf.read(new), records)
    # Assert
    assert [(r.action, r.new, r.corpus) for r in records] == [("set_count", "3", "x")]
    assert conflicts == [] and not extra and not missing
    back = diff.diff(lmf.read(new), lmf.read(base), lexicon="tst", user="ann",
                     source="rebuild", reason="test")
    assert [(r.action, r.old, r.new) for r in back] == [("set_count", "3", "0")]
    assert diff.residual(lmf.read(new), lmf.read(base), back) == ([], {}, {})


def test_set_tag_sets_replaces_and_removes(base: Path) -> None:
    # Arrange
    tag = {"lemma": "ワンワン", "pos": "n", "category": "adjective-class"}
    # Act
    items, conflicts = run(
        base,
        change("set_tag", 1, new="na", **tag),
        change("set_tag", 2, new="na", **tag),
        change("set_tag", 3, old="no", new="na-no", **tag),
        change("set_tag", 4, old="na", new="no", **tag))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3"]
    assert [(t.category, t.text) for t in entries(items)["tst-n-3"].tags] == [
        ("adjective-class", "no")]
    again, conflicts = changes.apply(items, [change("set_tag", 5, new="", **tag)])
    assert conflicts == [] and entries(again)["tst-n-3"].tags == []


def test_a_model_is_not_a_source_for_a_tag_but_may_remove_one() -> None:
    # Arrange
    tag = {"lemma": "犬", "pos": "n", "category": "adjective-class"}
    # Act
    adds = changes.validate(Change(id="c1", action="set_tag", lexicon="tst", user="ann",
                                   source="model: x", reason="test", new="na", **tag))
    removes = changes.validate(Change(id="c2", action="set_tag", lexicon="tst", user="ann",
                                      source="model: x", reason="test", new="", **tag))
    # Assert
    assert adds == ["a model alone is not a source for an addition"]
    assert removes == []


def test_a_rejected_sense_relation_cannot_be_added_later(base: Path) -> None:
    # Arrange
    pair = {"synset": "tst-1-n", "lemma": "ワンワン", "target": "tst-2-n", "target_lemma": "犬"}
    back = {"synset": "tst-2-n", "lemma": "犬", "target": "tst-1-n", "target_lemma": "ワンワン"}
    other = {"synset": "tst-1-n", "lemma": "狗", "target": "tst-2-n", "target_lemma": "犬"}
    # Act
    items, conflicts = run(
        base,
        change("reject_sense_relation", 1, **pair),
        change("add_sense_relation", 2, link="derivation", **pair),
        change("add_sense_relation", 3, link="derivation", **back),
        change("add_sense_relation", 4, link="derivation", **other),
        change("reject_sense_relation", 5, **other),
        change("reject_sense_relation", 6, link="other", **back),
        change("reject_sense_relation", 7, synset="tst-8-n", lemma="無", target="tst-2-n",
               target_lemma="犬"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c5"]
    assert "rejected by c1" in conflicts[0]
    assert entries(items)["tst-n-3"].senses[0].relations == []
    assert len(entries(items)["tst-n-2"].senses[0].relations) == 1


def test_diff_covers_tags(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    new.write_text(XML.replace('<Lemma writtenForm="ワンワン" partOfSpeech="n" />',
                               '<Lemma writtenForm="ワンワン" partOfSpeech="n">'
                               '<Tag category="adjective-class">na</Tag></Lemma>'),
                   encoding="utf-8")
    # Act
    records = diff.diff(lmf.read(base), lmf.read(new), lexicon="tst", user="ann",
                        source="rebuild", reason="test")
    back = diff.diff(lmf.read(new), lmf.read(base), lexicon="tst", user="ann",
                     source="rebuild", reason="test")
    # Assert
    assert [(r.action, r.category, r.old, r.new) for r in records] == [
        ("set_tag", "adjective-class", "", "na")]
    assert diff.residual(lmf.read(base), lmf.read(new), records) == ([], {}, {})
    assert [(r.action, r.old, r.new) for r in back] == [("set_tag", "na", "")]
    assert diff.residual(lmf.read(new), lmf.read(base), back) == ([], {}, {})


def test_remove_synset_needs_the_synset_to_be_empty(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("remove_synset", 1, synset="tst-3-n"),
        change("remove_sense", 2, synset="tst-3-n", lemma="犬"),
        change("remove_synset", 3, synset="tst-3-n"),
        change("remove_synset", 4, synset="tst-3-n"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c1", "c4"]
    assert "tst-3-n" not in synsets(items)


def test_diff_drops_a_synset_that_is_gone(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    start = XML.index('    <LexicalEntry id="tst-n-1">')
    end = XML.index('    <LexicalEntry id="tst-n-2">')
    text = XML[:start] + XML[end:]
    start = text.index('    <Synset id="tst-3-n"')
    new.write_text(text[:start] + "  </Lexicon>\n</LexicalResource>\n", encoding="utf-8")
    # Act
    records = diff.diff(lmf.read(base), lmf.read(new), lexicon="tst", user="ann",
                        source="rebuild", reason="test")
    # Assert
    assert [r.action for r in records] == ["remove_sense", "remove_synset", "remove_form"]
    assert diff.residual(lmf.read(base), lmf.read(new), records) == ([], {}, {})


def test_drop_empty_synsets_keeps_what_says_something(base: Path) -> None:
    # Arrange
    items, _ = run(
        base,
        change("remove_sense", 1, synset="tst-3-n", lemma="犬"),
        change("remove_sense", 2, synset="tst-2-n", lemma="犬"),
        change("add_synset", 3, synset="tst-8-n", pos="n", new="a gap we define"),
        change("add_synset", 4, synset="tst-9-n", pos="n", new="", identifier="ntumc00001"))
    synsets(items)["tst-9-n"].definitions = []
    # Act
    kept, dropped = changes.drop_empty_synsets(items)
    # Assert
    assert dropped == ["tst-2-n", "tst-3-n"]
    assert set(synsets(kept)) == {"tst-1-n", "tst-8-n", "tst-9-n"}
    assert synsets(kept)["tst-1-n"].relations == []  # its hypernym is gone


def test_set_pronunciation_sets_checks_and_removes(base: Path) -> None:
    # Arrange
    word = {"lemma": "ワンワン", "pos": "n"}
    # Act
    items, conflicts = run(
        base,
        change("set_pronunciation", 1, new="wan wan", notation="composed", **word),
        change("set_pronunciation", 2, new="wan wan", notation="composed", **word),
        change("set_pronunciation", 3, old="x", new="wanwan", **word),
        change("set_pronunciation", 4, old="wan wan", new="wanwan", **word))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3"]
    said = entries(items)["tst-n-3"].pronunciations
    assert [(p.text, p.notation) for p in said] == [("wanwan", None)]
    again, conflicts = changes.apply(items, [change("set_pronunciation", 5, new="", **word)])
    assert conflicts == [] and entries(again)["tst-n-3"].pronunciations == []
    model = Change(id="c6", action="set_pronunciation", lexicon="tst", user="ann",
                   source="model: x", reason="test", new="wan", **word)
    assert changes.validate(model) == ["a model alone is not a source for an addition"]


def test_add_synset_without_a_definition(base: Path) -> None:
    # Act
    items, conflicts = run(base, change("add_synset", 1, synset="tst-7-n", pos="n", new="",
                                        ili="i7"))
    # Assert
    assert conflicts == []
    assert (synsets(items)["tst-7-n"].definitions, synsets(items)["tst-7-n"].ili) == ([], "i7")


def test_set_identifier_sets_checks_and_removes(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("set_identifier", 1, synset="tst-1-n", new="ntumc00001"),
        change("set_identifier", 2, synset="tst-1-n", new="ntumc00001"),
        change("set_identifier", 3, synset="tst-1-n", old="", new="ntumc00002"),
        change("set_identifier", 4, synset="tst-0-n", new="ntumc00003"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c4"]
    assert synsets(items)["tst-1-n"].meta == {"dc:identifier": "ntumc00001"}
    again, conflicts = changes.apply(items, [change("set_identifier", 5, synset="tst-1-n",
                                                    old="ntumc00001", new="")])
    assert conflicts == [] and synsets(again)["tst-1-n"].meta == {}


def test_set_pos_moves_the_senses_to_entries_of_that_pos(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("set_pos", 1, synset="tst-1-n", old="n", new="v"),
        change("set_pos", 2, synset="tst-1-n", new="v"),
        change("set_pos", 3, synset="tst-1-n", old="n", new="a"),
        change("set_pos", 4, synset="tst-0-n", new="v"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c4"]
    assert synsets(items)["tst-1-n"].pos == "v"
    members = {str(e.lemma): (e.pos, [s.id for s in e.senses if s.synset == "tst-1-n"])
               for e in entries(items).values()
               if any(s.synset == "tst-1-n" for s in e.senses)}
    assert {pos for pos, _ in members.values()} == {"v"}
    assert sorted(s for _, ids in members.values() for s in ids) == sorted(
        synsets(items)["tst-1-n"].members.split())
    assert "tst-n-3" not in entries(items)  # ワンワン (n) had no other sense


def test_set_note_sets_checks_and_removes(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("set_note", 1, synset="tst-1-n", lemma="ワンワン", old="", new="child's word"),
        change("set_note", 2, synset="tst-1-n", lemma="ワンワン", new="child's word"),
        change("set_note", 3, synset="tst-1-n", lemma="ワンワン", old="other", new="x"),
        change("set_note", 4, synset="tst-1-n", lemma="なし", new="x"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c4"]
    assert entries(items)["tst-n-3"].senses[0].meta["note"] == "child's word"
    again, conflicts = changes.apply(items, [change("set_note", 5, synset="tst-1-n",
                                                    lemma="ワンワン", new="")])
    assert conflicts == [] and "note" not in entries(again)["tst-n-3"].senses[0].meta


def test_set_frames_sets_checks_and_removes(base: Path) -> None:
    # Arrange
    base.write_text(XML.replace("</Lexicon>", """<SyntacticBehaviour id="tst-f1"
        subcategorizationFrame="NP V" /><SyntacticBehaviour id="tst-f2"
        subcategorizationFrame="NP V NP" /></Lexicon>"""), encoding="utf-8")
    # Act
    items, conflicts = run(
        base,
        change("set_frames", 1, synset="tst-1-n", lemma="ワンワン", new="tst-f1 tst-f2"),
        change("set_frames", 2, synset="tst-1-n", lemma="ワンワン", new="tst-f1 tst-f2"),
        change("set_frames", 3, synset="tst-1-n", lemma="ワンワン", new="tst-f9"),
        change("set_frames", 4, synset="tst-1-n", lemma="ワンワン", old="tst-f1", new=""),
        change("set_frames", 5, synset="tst-1-n", lemma="ワンワン", old="tst-f1 tst-f2",
               new="tst-f2"))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c4"]
    assert entries(items)["tst-n-3"].senses[0].subcat == "tst-f2"
    again, conflicts = changes.apply(items, [change("set_frames", 6, synset="tst-1-n",
                                                    lemma="ワンワン", new="")])
    assert conflicts == [] and entries(again)["tst-n-3"].senses[0].subcat is None


def test_set_ili_sets_checks_and_removes(base: Path) -> None:
    # Act
    items, conflicts = run(
        base,
        change("set_ili", 1, synset="tst-1-n", old="i1", new="i9"),
        change("set_ili", 2, synset="tst-1-n", new="i9"),
        change("set_ili", 3, synset="tst-1-n", old="i1", new="i8"),
        change("set_ili", 4, synset="tst-2-n", new="i9"),
        change("set_ili", 5, synset="tst-0-n", new="i7"),
        change("set_ili", 6, synset="tst-2-n", new=""))
    # Assert
    assert [c.split(":")[0] for c in conflicts] == ["c2", "c3", "c4", "c5"]
    assert (synsets(items)["tst-1-n"].ili, synsets(items)["tst-2-n"].ili) == ("i9", "")


def test_diff_covers_ilis(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    new.write_text(XML.replace('<Synset id="tst-2-n" ili="i2"', '<Synset id="tst-2-n" ili="i9"'),
                   encoding="utf-8")
    # Act
    records = diff.diff(lmf.read(base), lmf.read(new), lexicon="tst", user="ann",
                        source="rebuild", reason="test")
    # Assert
    assert [(r.action, r.synset, r.old, r.new) for r in records] == [
        ("set_ili", "tst-2-n", "i2", "i9")]
    assert diff.residual(lmf.read(base), lmf.read(new), records) == ([], {}, {})


def test_diff_covers_identifiers(base: Path, tmp_path: Path) -> None:
    # Arrange
    new = tmp_path / "new.xml"
    new.write_text(XML.replace('<Synset id="tst-2-n" ili="i2"',
                               '<Synset id="tst-2-n" ili="i2" dc:identifier="ntumc00002"'),
                   encoding="utf-8")
    # Act
    records = diff.diff(lmf.read(base), lmf.read(new), lexicon="tst", user="ann",
                        source="rebuild", reason="test")
    # Assert
    assert [(r.action, r.synset, r.old, r.new) for r in records] == [
        ("set_identifier", "tst-2-n", "", "ntumc00002")]
    assert diff.residual(lmf.read(base), lmf.read(new), records) == ([], {}, {})
