"""Tests for ntumc.wordnet.shared: the minimal lexicon and its export."""

import hashlib

import pytest

from ntumc.wordnet import lmf, shared
from ntumc.wordnet.diff import facts
from ntumc.wordnet.model import Lexicon, Relation, Requires, Synset, Text


def concepts() -> list:
    """A shared lexicon: one concept, related to a Princeton synset and an absent one."""
    return [
        Lexicon(id="omw-ntumc", version="0.1"),
        Synset(id="omw-ntumc-00001-n", pos="n", ili="in",
               meta={"dc:identifier": "ntumc00001"},
               definitions=[Text(text="a four-character idiom", lang="en")],
               relations=[Relation(link="hypernym", target="omw-ntumc-i1-n"),
                          Relation(link="similar", target="omw-ntumc-i2-n")]),
        Synset(id="omw-ntumc-i1-n", pos="n", ili="i1"),
        Synset(id="omw-ntumc-i2-n", pos="n", ili="i2"),
    ]


def lexicon(definition: Text, relations: list[Relation]) -> list:
    """A lexicon with the concept and the Princeton synset ``i1``."""
    return [
        Lexicon(id="cow", label="COW", requires=[Requires(ref="omw-en", version="2.0")]),
        Synset(id="cow-7-n", pos="n", ili="", meta={"dc:identifier": "ntumc00001"},
               definitions=[definition], relations=relations),
        Synset(id="cow-1-n", pos="n", ili="i1"),
    ]


def test_minimal_takes_out_what_the_shared_lexicon_says():
    items = lexicon(Text(text="a four-character idiom", lang="en"),
                    [Relation(link="hypernym", target="cow-1-n"),
                     Relation(link="domain_topic", target="cow-1-n")])

    mini, counts = shared.minimal(items, concepts())

    assert counts == {"concepts": 1, "definitions": 1, "relations": 1}
    assert mini[0].id == "cow-min"
    assert [(r.ref, r.version) for r in mini[0].requires] == [("omw-en", "2.0"),
                                                              ("omw-ntumc", "0.1")]
    assert mini[1].definitions == []
    assert [(r.link, r.target) for r in mini[1].relations] == [("domain_topic", "cow-1-n")]


def test_export_restores_the_lexicon():
    def full() -> list:
        return lexicon(Text(text="a four-character idiom", lang="en"),
                       [Relation(link="hypernym", target="cow-1-n"),
                        Relation(link="domain_topic", target="cow-1-n")])
    mini, _ = shared.minimal(full(), concepts())

    out, counts = shared.export(mini, concepts())

    assert counts == {"concepts": 1, "definitions": 1, "relations": 1}
    assert out[0].id == "cow" and out[0].label == "COW"
    assert [r.ref for r in out[0].requires] == ["omw-en"]
    assert facts(out) == facts(full())


def test_a_definition_of_its_own_stays_and_the_shared_one_is_added_in_another_language():
    items = lexicon(Text(text="四个字的成语"), [])
    items[0].language = "cmn-Hans"

    mini, counts = shared.minimal(items, concepts())
    kept = [d.text for d in mini[1].definitions]
    out, added = shared.export(mini, concepts())

    assert counts["definitions"] == 0
    assert kept == ["四个字的成语"]
    assert added["definitions"] == 1
    assert [(d.lang, d.text) for d in out[1].definitions] == [
        (None, "四个字的成语"), ("en", "a four-character idiom")]


def test_a_definition_of_its_own_in_the_shared_language_is_not_added_to():
    items = lexicon(Text(text="an idiom of four characters", lang="en"), [])

    mini, counts = shared.minimal(items, concepts())
    out, added = shared.export(mini, concepts())

    assert counts["definitions"] == 0 and added["definitions"] == 0
    assert [d.text for d in out[1].definitions] == ["an idiom of four characters"]


def test_a_definition_with_no_language_is_in_the_lexicon_s_language():
    items = lexicon(Text(text="an idiom of four characters"), [])
    items[0].language = "en"

    mini, _ = shared.minimal(items, concepts())
    out, added = shared.export(mini, concepts())

    assert added["definitions"] == 0
    assert [d.text for d in out[1].definitions] == ["an idiom of four characters"]


def test_minimal_takes_out_the_shared_definition_and_keeps_the_one_in_another_language():
    def full() -> list:
        items = lexicon(Text(text="四个字的成语"), [Relation(link="hypernym", target="cow-1-n")])
        items[0].language = "cmn-Hans"
        items[1].definitions.append(Text(text="a four-character idiom", lang="en"))
        return items

    mini, counts = shared.minimal(full(), concepts())
    kept = [d.text for d in mini[1].definitions]
    out, _ = shared.export(mini, concepts())

    assert counts["definitions"] == 1
    assert kept == ["四个字的成语"]
    assert facts(out) == facts(full())


def test_export_adds_a_relation_once_its_target_is_there():
    items = lexicon(Text(text="四个字的成语"), [])
    mini, _ = shared.minimal(items, concepts())

    out, counts = shared.export(mini, concepts())

    assert counts["relations"] == 1  # hypernym to i1; i2 is not in the lexicon
    assert [(r.link, r.target) for r in out[1].relations] == [("hypernym", "cow-1-n")]


def test_export_wants_a_minimal_lexicon():
    with pytest.raises(ValueError, match="not a minimal lexicon"):
        shared.export(lexicon(Text(text="x"), []), concepts())


def test_a_shared_identifier_on_two_synsets_is_an_error():
    items = lexicon(Text(text="x"), [])
    items.append(Synset(id="cow-8-n", pos="n", meta={"dc:identifier": "ntumc00001"}))

    with pytest.raises(ValueError, match="ntumc00001 is on"):
        shared.minimal(items, concepts())


def test_another_lexicon_s_identifier_may_repeat():
    items = lexicon(Text(text="x"), [])
    items += [Synset(id="cow-9-a", pos="a", meta={"dc:identifier": "pronoun:1;Sg"}),
              Synset(id="cow-9-n", pos="n", meta={"dc:identifier": "pronoun:1;Sg"})]

    _, counts = shared.minimal(items, concepts())

    assert counts["concepts"] == 1


def test_write_release_writes_both_and_load_checks_the_pin(tmp_path):
    dc = {"dc": "https://globalwordnet.github.io/schemas/dc/"}
    source = tmp_path / "omw-ntumc-0.1.xml"
    their = concepts()
    their[0].namespaces = dc
    lmf.write(source, their)
    pin = hashlib.sha256(source.read_bytes()).hexdigest()
    items = lexicon(Text(text="a four-character idiom", lang="en"),
                    [Relation(link="hypernym", target="cow-1-n")])
    items[0].version = "1.2"
    items[0].namespaces = dc

    small = shared.write_release(items, shared.load(source, pin), tmp_path / "cow-1.2.xml")

    assert small.name == "cow-min-1.2.xml"
    assert next(lmf.read(small)).id == "cow-min"
    assert next(lmf.read(tmp_path / "cow-1.2.xml")).id == "cow"
    with pytest.raises(ValueError, match="not the pinned version"):
        shared.load(source, "0" * 64)
