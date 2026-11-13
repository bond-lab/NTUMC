"""Tests for the lossless wordnet model (ntumc.wordnet)."""

import sqlite3
from pathlib import Path

import pytest

from ntumc.wordnet import jsonl, store
from ntumc.wordnet.__main__ import check, dump, load
from ntumc.wordnet.model import Entry, Gloss, Row, Synset

SCHEMA = """
CREATE TABLE meta (attr TEXT, lang TEXT, val TEXT);
CREATE TABLE synset (synset TEXT primary key, pos TEXT, name TEXT, src TEXT, usr TEXT);
CREATE TABLE word (wordid INTEGER primary key, lang TEXT, lemma TEXT, pron TEXT, pos TEXT, usr TEXT);
CREATE TABLE sense (synset TEXT, wordid INTEGER, lang TEXT, rank TEXT, lexid INTEGER,
                    freq INTEGER, src TEXT, confidence REAL, usr TEXT);
CREATE TABLE synlink (synset1 TEXT, synset2 TEXT, link TEXT, src TEXT, usr TEXT);
CREATE TABLE senslink (synset1 TEXT, wordid1 INTEGER, synset2 TEXT, wordid2 INTEGER,
                       link TEXT, src TEXT, usr TEXT);
CREATE TABLE xlink (synset TEXT, resource TEXT, xref TEXT, misc TEXT, confidence TEXT, usr TEXT);
CREATE TABLE xlinks (synset TEXT, wordid INTEGER, lang TEXT, resource TEXT, xref TEXT,
                     misc TEXT, confidence TEXT, usr TEXT);
CREATE TABLE synset_def (synset TEXT, lang TEXT, def TEXT, sid INTEGER, usr TEXT);
CREATE TABLE synset_ex (synset TEXT, lang TEXT, def TEXT, sid INTEGER, usr TEXT);
CREATE TABLE synset_comment (synset TEXT NOT NULL, comment TEXT NOT NULL, u TEXT NOT NULL,
                             t TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE sense_log (synset_new TEXT, synset_old TEXT, date_update DATE);
CREATE INDEX sense_synset ON sense (synset);
CREATE TRIGGER insert_sense_log AFTER INSERT ON sense BEGIN
  INSERT INTO sense_log (synset_new, date_update) VALUES (new.synset, DATETIME('NOW')); END;
"""
DATA = """
INSERT INTO meta VALUES ('name', 'mul', 'test');
INSERT INTO synset VALUES ('00000001-n', 'n', 'dog', 'eng30', NULL), ('00000002-n', 'n', 'animal', 'eng30', '');
INSERT INTO word VALUES (1, 'eng', 'dog', NULL, 'n', NULL), (2, 'jpn', '犬', NULL, 'n', 'ann'),
                        (3, 'jpn', '語', NULL, 'n', NULL);
INSERT INTO sense VALUES ('00000001-n', 1, 'eng', '0', NULL, 3, 'eng30', 1.0, NULL),
                         ('00000001-n', 2, 'jpn', NULL, NULL, NULL, 'jpn', 0.8, 'ann'),
                         ('00000001-n', 2, 'jpn', NULL, NULL, NULL, 'jpn', 0.8, 'ann'),
                         ('00000009-n', 99, 'jpn', NULL, NULL, NULL, 'lost', 1.0, NULL);
INSERT INTO synlink VALUES ('00000001-n', '00000002-n', 'hype', 'eng30', NULL),
                           ('00000008-n', '00000002-n', 'hype', 'gone', NULL);
INSERT INTO senslink VALUES ('00000001-n', 1, '00000002-n', 1, 'derv', 'eng30', NULL);
INSERT INTO xlink VALUES ('00000001-n', 'lexnames', 'noun.animal', NULL, NULL, NULL);
INSERT INTO xlinks VALUES ('00000001-n', 1, 'eng', 'lvframes', '1', NULL, NULL, NULL);
INSERT INTO synset_def VALUES ('00000001-n', 'eng', 'a canine', 0, NULL), ('00000001-n', 'eng', 'a pet', 1, NULL),
                              ('00000001-n', 'jpn', '', 0, NULL);
INSERT INTO synset_ex VALUES ('00000001-n', 'eng', 'the dog barked', 0, NULL);
INSERT INTO synset_comment VALUES ('00000001-n', 'check this', 'ann', '2020-01-01 00:00:00');
DELETE FROM sense_log;
INSERT INTO sense_log VALUES ('00000001-n', NULL, '2015-01-01 00:00:00');
"""


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "wn.db"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA + DATA)
    con.close()
    return path


def test_round_trip_is_identical(db: Path, tmp_path: Path) -> None:
    # Act
    diffs = check(db, tmp_path / "work")
    # Assert
    assert diffs == []


def test_load_does_not_fire_log_triggers(db: Path, tmp_path: Path) -> None:
    # Arrange
    dump(db, tmp_path / "dump")
    # Act
    load(tmp_path / "dump", tmp_path / "new.db")
    # Assert
    con = sqlite3.connect(tmp_path / "new.db")
    assert con.execute("SELECT count(*) FROM sense_log").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0] == 1


def test_read_nests_children_and_keeps_orphans(db: Path) -> None:
    # Act
    items = list(store.read(db))
    # Assert
    dog = next(i for i in items if isinstance(i, Synset) and i.id == "00000001-n")
    assert [r.target for r in dog.relations] == ["00000002-n"]
    assert dog.xlinks[0].xref == "noun.animal" and dog.comments[0].u == "ann"
    inu = next(i for i in items if isinstance(i, Entry) and i.lemma == "犬")
    assert len(inu.senses) == 2  # the duplicated sense row is kept twice
    eng = next(i for i in items if isinstance(i, Gloss) and i.lang == "eng")
    assert [d.text for d in eng.definitions] == ["a canine", "a pet"]
    orphans = {(i.table, i.values.get("src")) for i in items if isinstance(i, Row)}
    assert ("sense", "lost") in orphans and ("synlink", "gone") in orphans


def test_empty_string_is_not_none(db: Path) -> None:
    # Arrange
    animal = next(i for i in store.read(db) if isinstance(i, Synset) and i.id == "00000002-n")
    # Act
    line = jsonl.dumps(animal)
    # Assert
    assert '"usr": ""' in line
    assert jsonl.loads(line) == animal


def test_no_history_leaves_out_logs(db: Path, tmp_path: Path) -> None:
    # Act
    counts = dump(db, tmp_path / "dump", history=False)
    # Assert
    assert "history" not in counts
    assert {"concepts", "eng", "jpn", "other"} <= set(counts)


def test_compare_reports_a_changed_row(db: Path, tmp_path: Path) -> None:
    # Arrange
    dump(db, tmp_path / "dump")
    load(tmp_path / "dump", tmp_path / "new.db")
    con = sqlite3.connect(tmp_path / "new.db")
    con.execute("UPDATE word SET lemma = 'hound' WHERE wordid = 1")
    con.commit()
    con.close()
    # Act
    diffs = store.compare(db, tmp_path / "new.db")
    # Assert
    assert any(d.startswith("word:") for d in diffs)


def test_unknown_column_is_an_error(db: Path) -> None:
    # Arrange
    con = sqlite3.connect(db)
    con.execute("ALTER TABLE sense ADD COLUMN note TEXT")
    con.commit()
    con.close()
    # Act / Assert
    with pytest.raises(ValueError, match="note"):
        list(store.read(db))
