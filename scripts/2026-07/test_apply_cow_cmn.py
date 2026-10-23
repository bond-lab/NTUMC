"""Tests for apply_cow_cmn.py (Jia Qi's Chinese wordnet edits)."""

import sqlite3

import pytest
from apply_cow_cmn import Applier, Row, choose, lemma_forms, split


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Tiny wordnet: one synset with a Chinese definition and two senses."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE word (wordid INTEGER PRIMARY KEY, lang TEXT, lemma TEXT,
                           pron TEXT, pos TEXT, usr TEXT);
        CREATE TABLE sense (synset TEXT, wordid INTEGER, lang TEXT, rank TEXT,
                            lexid INTEGER, freq INTEGER, src TEXT,
                            confidence REAL, usr TEXT);
        CREATE TABLE synset_def (synset TEXT, lang TEXT, def TEXT, sid INTEGER,
                                 usr TEXT);
        INSERT INTO word VALUES (1, 'cmn', '年轻+的', NULL, 'a', NULL);
        INSERT INTO word VALUES (2, 'cmn', '年轻', NULL, 'a', NULL);
        INSERT INTO sense (synset, wordid, lang) VALUES ('01554510-a', 1, 'cmn');
        INSERT INTO sense (synset, wordid, lang) VALUES ('01554510-a', 2, 'cmn');
        INSERT INTO synset_def VALUES ('01554510-a', 'cmn', '旧的', 0, NULL);
        """
    )
    return conn


def row(sheet: str, definition: str, easy: str = "") -> Row:
    """A spreadsheet row for synset 03365991-n."""
    return Row(sheet, "03365991-n", "a floor", definition, easy)


def test_split_handles_all_separators() -> None:
    """Lemmas split on ; ； and 、 with blanks dropped."""
    assert split("甲; 乙；丙、丁; ") == ["甲", "乙", "丙", "丁"]


def test_lemma_forms_matches_plus_de() -> None:
    """X的 also matches the wordnet's X+的."""
    assert lemma_forms("年轻的") == ["年轻的", "年轻+的"]
    assert lemma_forms("年轻+的") == ["年轻+的"]


def test_choose_prefers_cmn_edu_then_easy() -> None:
    """cmn_edu wins a pair; an EASY_WINS synset uses its easy definition."""
    rows = [row("cmn_edu", "甲", easy="楼房的一层"), row("tufs_lexicon", "乙")]

    chosen, review = choose(rows)

    assert chosen == "楼房的一层"
    kinds = {(k, t) for _, k, t in review}
    assert ("alt_def", "乙") in kinds
    assert ("full_def_replaced_by_easy", "甲") in kinds


def test_set_definition_replaces_old(conn: sqlite3.Connection) -> None:
    """A new definition replaces a different existing one."""
    app = Applier(conn, dry_run=False)

    replaced = app.set_definition("01554510-a", "年纪不大的")

    defs = [d for (d,) in conn.execute("SELECT def FROM synset_def")]
    assert defs == ["年纪不大的"]
    assert replaced == ["旧的"]


def test_delete_and_add_lemmas(conn: sqlite3.Connection) -> None:
    """Deleting 年轻的 removes 年轻+的; adding creates word and sense."""
    app = Applier(conn, dry_run=False)

    assert app.delete_lemma("01554510-a", "年轻的")
    assert not app.delete_lemma("01554510-a", "老")
    app.add_lemma("01554510-a", "少")

    lemmas = {lem for (lem,) in conn.execute(
        "SELECT lemma FROM sense JOIN word USING (wordid)")}
    assert lemmas == {"年轻", "少"}


def test_dry_run_changes_nothing(conn: sqlite3.Connection) -> None:
    """A dry run leaves senses and definitions alone."""
    app = Applier(conn, dry_run=True)

    app.set_definition("01554510-a", "新")
    app.delete_lemma("01554510-a", "年轻")
    app.add_lemma("01554510-a", "少")

    assert conn.execute("SELECT count(*) FROM sense").fetchone()[0] == 2
    assert conn.execute("SELECT def FROM synset_def").fetchone()[0] == "旧的"
