"""Tests for make_concordance.py and english_additions.py."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import english_additions
import make_concordance

from ntumc.corpus import Sentence, Word


def sentence(text: str, words: list[str]) -> Sentence:
    """A sentence whose words have ids from 0 and no offsets."""
    return Sentence(1, text, words=[Word(i, w) for i, w in enumerate(words)])


def test_kwic_splits_at_the_concept_words():
    sent = sentence("I like chilli crab.", ["I", "like", "chilli", "crab", "."])

    parts = make_concordance.kwic(sent, [2, 3])

    assert parts == ("I like", "chilli crab", ".")


def test_kwic_keeps_text_without_spaces_together():
    sent = sentence("我爱辣蟹。", ["我", "爱", "辣蟹", "。"])

    parts = make_concordance.kwic(sent, [2])

    assert parts == ("我爱", "辣蟹", "。")


def test_kwic_of_a_concept_with_no_words_is_the_sentence():
    sent = sentence("Go on.", ["Go", "on", "."])

    assert make_concordance.kwic(sent, [9]) == ("Go on.", "", "")


def test_shard_is_stable_and_in_range():
    assert make_concordance.shard("80002015-n") == 80002015 % make_concordance.SHARDS


def test_cut_keeps_additions_and_stubs_of_their_synsets():
    root = ET.fromstring("""<LexicalResource><Lexicon id="ntumc-en-min">
      <LexicalEntry id="oewn-tea-n"><Lemma writtenForm="tea" partOfSpeech="n"/>
        <Sense id="oewn-tea-1" synset="oewn-1-n"/>
        <Sense id="ntumc-en-tea-2-n" synset="oewn-2-n"><SenseRelation relType="similar" target="oewn-tea-1"/></Sense>
      </LexicalEntry>
      <LexicalEntry id="oewn-cup-n"><Lemma writtenForm="cup" partOfSpeech="n"/>
        <Sense id="oewn-cup-1" synset="oewn-1-n"/></LexicalEntry>
      <Synset id="oewn-1-n" ili="i1" partOfSpeech="n"><Definition>one</Definition></Synset>
      <Synset id="oewn-2-n" ili="i2" partOfSpeech="n" members="oewn-tea-n"><Definition>two</Definition>
        <SynsetRelation relType="hypernym" target="oewn-1-n"/></Synset>
      <Synset id="ntumc-en-3-n" ili="" partOfSpeech="n">
        <SynsetRelation relType="hypernym" target="oewn-2-n"/>
        <SynsetRelation relType="hypernym" target="oewn-1-n"/></Synset>
    </Lexicon></LexicalResource>""")

    counts = english_additions.cut(root)

    lexicon = root.find("Lexicon")
    assert counts == (1, 1, 2)
    assert [s.get("id") for s in lexicon.iter("Sense")] == ["ntumc-en-tea-2-n"]
    assert lexicon.find(".//SenseRelation") is None
    stub = lexicon.find("Synset[@id='oewn-2-n']")
    assert len(stub) == 0 and stub.get("members") is None
    own = lexicon.find("Synset[@id='ntumc-en-3-n']")
    assert [r.get("target") for r in own] == ["oewn-2-n"]
