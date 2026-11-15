"""Tests of ntumc.wordnet.validate, which runs wn's validation."""

import logging
from pathlib import Path

import pytest

from ntumc.wordnet import validate

pytest.importorskip("wn")

DOCTYPE = ('<!DOCTYPE LexicalResource SYSTEM '
           '"http://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd">')
XML = f"""<?xml version="1.0" encoding="UTF-8"?>
{DOCTYPE}
<LexicalResource xmlns:dc="https://globalwordnet.github.io/schemas/dc/">
  <Lexicon id="tst" label="Test" language="ja" email="x@example.org"
           license="https://example.org/" version="1">
    <LexicalEntry id="tst-n-1">
      <Lemma writtenForm="犬" partOfSpeech="n" />
      <Sense id="tst-1-n-1" synset="tst-1-n" />
    </LexicalEntry>
    <Synset id="tst-1-n" ili="i1" partOfSpeech="n" members="tst-1-n-1" />
    <Synset id="tst-2-n" ili="i2" partOfSpeech="n" />
  </Lexicon>
</LexicalResource>
"""


def test_check_passes_a_file_with_only_other_warnings(tmp_path: Path, caplog) -> None:
    # Arrange
    xml = tmp_path / "good.xml"
    xml.write_text(XML, encoding="utf-8")
    # Act
    with caplog.at_level(logging.INFO):
        good = validate.check(xml)
    # Assert
    assert good
    assert "W301" in caplog.text  # tst-2-n is empty: counted, not fatal


def test_check_fails_an_ili_on_two_synsets(tmp_path: Path, caplog) -> None:
    # Arrange
    xml = tmp_path / "shared.xml"
    xml.write_text(XML.replace('ili="i2"', 'ili="i1"'), encoding="utf-8")
    # Act
    good = validate.check(xml)
    # Assert
    assert not good
    assert "W302" in caplog.text and "tst-2-n" in caplog.text


def test_check_fails_an_error(tmp_path: Path) -> None:
    # Arrange
    xml = tmp_path / "missing.xml"
    xml.write_text(XML.replace('synset="tst-1-n"', 'synset="tst-9-n"'),
                   encoding="utf-8")
    # Act
    found = validate.report(xml)
    # Assert
    assert "E204" in found
    assert not validate.check(xml)


def test_check_says_so_when_wn_is_missing(tmp_path: Path, monkeypatch, caplog) -> None:
    # Arrange
    def no_wn(xml: Path) -> dict:
        raise ImportError("wn")
    monkeypatch.setattr(validate, "report", no_wn)
    # Act
    good = validate.check(tmp_path / "any.xml")
    # Assert
    assert good
    assert "not validated" in caplog.text


def test_check_fails_a_word_twice_in_a_synset(tmp_path: Path, caplog) -> None:
    # Arrange
    xml = tmp_path / "twice.xml"
    sense = '<Sense id="tst-1-n-1" synset="tst-1-n" />'
    xml.write_text(XML.replace(sense, sense + sense.replace("n-1", "n-2")),
                   encoding="utf-8")
    # Act
    good = validate.check(xml)
    lenient = validate.check(xml, fail=("E",))
    # Assert
    assert not good and lenient
    assert "W202" in caplog.text
