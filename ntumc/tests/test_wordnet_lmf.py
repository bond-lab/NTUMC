"""Tests for WN-LMF in and out of the wordnet model (ntumc.wordnet.lmf)."""

from pathlib import Path

import pytest

from ntumc.wordnet import jsonl, lmf
from ntumc.wordnet.__main__ import check_lmf
from ntumc.wordnet.model import Entry, Lexicon, Row, Synset

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE LexicalResource SYSTEM "https://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd">
<LexicalResource xmlns:dc="https://globalwordnet.github.io/schemas/dc/">
  <!-- a comment, which is not kept -->
  <Lexicon id="tst" label="Test &amp; more" language="ja" email="a@example.org"
           license="CC BY 4.0" version="1" dc:publisher="us">
    <Requires ref="omw-en" version="1.4" />
    <LexicalEntry id="tst-n-1" dc:contributor="ann" note="check">
      <Lemma writtenForm="犬" partOfSpeech="n" script="Jpan">
        <Pronunciation notation="ipa">inu</Pronunciation>
        <Tag category="class">animate</Tag>
      </Lemma>
      <Form writtenForm="いぬ" script="hira"><Tag category="kind">reading</Tag></Form>
      <Sense id="tst-1-n-1" synset="tst-1-n" confidenceScore="0.80" lexicalized="true">
        <SenseRelation relType="derivation" target="tst-2-n-1" dc:source="x" />
        <Example language="ja">犬が &lt;吠えた&gt;</Example>
        <Count dc:source="JSemCor">46</Count>
      </Sense>
      <Sense id="tst-2-n-1" synset="tst-2-n" />
      <SyntacticBehaviour id="f1" subcategorizationFrame="NP V" senses="tst-1-n-1" />
    </LexicalEntry>
    <LexicalEntry id="tst-n-2"><Lemma writtenForm="x" partOfSpeech="n" /></LexicalEntry>
    <Synset id="tst-1-n" ili="in" partOfSpeech="n" members="tst-1-n-1" lexfile="noun.animal"
            dc:identifier="ntumc00001">
      <Definition>a canine</Definition>
      <Definition language="ja" sourceSense="tst-1-n-1" dc:source="j"></Definition>
      <ILIDefinition>a domesticated canine animal</ILIDefinition>
      <SynsetRelation relType="hypernym" target="tst-2-n" />
      <Example>  spaces kept  </Example>
    </Synset>
    <Synset id="tst-2-n" ili="" partOfSpeech="n" lexicalized="false" />
    <SyntacticBehaviour id="f2" subcategorizationFrame="V" />
  </Lexicon>
</LexicalResource>
"""


@pytest.fixture
def xml(tmp_path: Path) -> Path:
    path = tmp_path / "tst.xml"
    path.write_text(XML, encoding="utf-8")
    return path


def test_round_trip_through_jsonl_is_identical(xml: Path, tmp_path: Path) -> None:
    # Act
    diffs = check_lmf(xml, tmp_path / "work")
    # Assert
    assert diffs == []


def test_read_fills_the_model(xml: Path) -> None:
    # Act
    items = list(lmf.read(xml))
    # Assert
    lexicon = items[0]
    assert isinstance(lexicon, Lexicon)
    assert lexicon.label == "Test & more" and lexicon.requires[0].ref == "omw-en"
    assert lexicon.meta == {"dc:publisher": "us"}
    inu = items[1]
    assert isinstance(inu, Entry)
    assert (inu.lemma, inu.pos, inu.script) == ("犬", "n", "Jpan")
    assert inu.meta == {"dc:contributor": "ann", "note": "check"}
    assert inu.forms[0].form == "いぬ" and inu.pronunciations[0].text == "inu"
    assert inu.senses[0].meta["confidenceScore"] == "0.80"  # the string as written
    assert inu.senses[0].counts[0].meta == {"dc:source": "JSemCor"}
    dog = next(i for i in items if isinstance(i, Synset))
    assert dog.meta == {"dc:identifier": "ntumc00001"} and dog.ili == "in"
    assert [d.text for d in dog.definitions] == ["a canine", ""]
    assert dog.examples[0].text == "  spaces kept  "
    assert items[-2].ili == "" and items[-1].frame == "V"


def test_unknown_attribute_is_an_error(xml: Path) -> None:
    # Arrange
    xml.write_text(XML.replace('lexfile="noun.animal"', 'colour="red"'), encoding="utf-8")
    # Act / Assert
    with pytest.raises(ValueError, match="colour"):
        list(lmf.read(xml))


def test_unknown_element_is_an_error(xml: Path) -> None:
    # Arrange
    xml.write_text(XML.replace("<Definition>a canine</Definition>", "<Note>hm</Note>"),
                   encoding="utf-8")
    # Act / Assert
    with pytest.raises(ValueError, match="Note"):
        list(lmf.read(xml))


@pytest.mark.parametrize(("old", "new"), [
    ("a canine", "a feline"),
    ('confidenceScore="0.80"', 'confidenceScore="0.8"'),
    ('<Synset id="tst-2-n" ili="" partOfSpeech="n" lexicalized="false" />', ""),
    ("WN-LMF-1.4.dtd", "WN-LMF-1.3.dtd"),
])
def test_compare_reports_a_difference(xml: Path, tmp_path: Path, old: str, new: str) -> None:
    # Arrange
    other = tmp_path / "other.xml"
    other.write_text(XML.replace(old, new), encoding="utf-8")
    # Act / Assert
    assert lmf.compare(xml, other)


def test_write_refuses_what_lmf_cannot_hold(tmp_path: Path) -> None:
    # Act / Assert
    with pytest.raises(ValueError, match="Row"):
        lmf.write(tmp_path / "x.xml", [Lexicon(id="x"), Row("meta", {})])
    with pytest.raises(ValueError, match="Lexicon"):
        lmf.write(tmp_path / "y.xml", [Synset(id="x")])


def test_empty_meta_is_left_out_of_jsonl() -> None:
    # Act
    line = jsonl.dumps(Synset(id="x-n", pos="n", ili=""))
    # Assert
    assert line == '{"kind": "synset", "id": "x-n", "pos": "n", "ili": ""}'
