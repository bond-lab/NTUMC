"""Tests for fix_eng_pos.py (2017 English POS/tokenisation fix port)."""

import json
import sqlite3

import pytest

from fix_eng_pos import TARGETS_FILE, Fixer, VAX_POS


@pytest.fixture
def fixer() -> Fixer:
    """Fixer over a tiny in-memory corpus database."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE sent (sid INTEGER PRIMARY KEY, sent TEXT,
                           comment TEXT, usrname TEXT);
        CREATE TABLE word (sid INTEGER, wid INTEGER, word TEXT, pos TEXT,
                           lemma TEXT, cfrom INTEGER, cto INTEGER,
                           comment TEXT, usrname TEXT,
                           PRIMARY KEY (sid, wid));
        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, tags TEXT, comment TEXT,
                              ntag TEXT, usrname TEXT,
                              PRIMARY KEY (sid, cid));
        CREATE TABLE cwl (sid INTEGER, wid INTEGER, cid INTEGER,
                          usrname TEXT);
        """
    )
    with open(TARGETS_FILE, encoding="utf-8") as fh:
        targets = json.load(fh)
    return Fixer(conn, targets)


def add_sentence(fixer: Fixer, sid: int, text: str,
                 words: list[tuple[str, str]]) -> None:
    """Insert a sentence and its (word, pos) tokens."""
    fixer.conn.execute("INSERT INTO sent (sid, sent) VALUES (?, ?)",
                       (sid, text))
    for wid, (word, pos) in enumerate(words):
        fixer.conn.execute(
            "INSERT INTO word (sid, wid, word, pos, lemma) "
            "VALUES (?, ?, ?, ?, ?)", (sid, wid, word, pos, word.lower()))


class TestMeasureParts:
    """Zm/Zp/Zu token splitting."""

    def test_percent(self, fixer: Fixer) -> None:
        assert fixer._measure_parts("50_%") == [
            ("50", "CD", "50"), ("%", "NN", "%")]

    def test_currency_amount(self, fixer: Fixer) -> None:
        parts = fixer._measure_parts("3,700_dollars")
        assert parts == [("3,700", "CD", "3,700"),
                         ("dollars", "NNS", "dollar")]

    def test_hong_kong_dollars(self, fixer: Fixer) -> None:
        parts = fixer._measure_parts("3,700_Hong_Kong_dollars")
        assert parts == [("3,700", "CD", "3,700"),
                         ("Hong_Kong_dollars", "NNPS", "Hong_Kong_dollar")]

    def test_canadian_dollars(self, fixer: Fixer) -> None:
        parts = fixer._measure_parts("six_million_Canadian_dollars")
        assert parts == [("six", "CD", "six"), ("million", "CD", "million"),
                         ("Canadian_dollars", "NNPS", "Canadian_dollar")]

    def test_hyphenated_billion(self, fixer: Fixer) -> None:
        parts = fixer._measure_parts("40-billion_yen")
        assert parts == [("40-billion", "CD", "40-billion"),
                         ("yen", "NN", "yen")]

    def test_article_fraction(self, fixer: Fixer) -> None:
        parts = fixer._measure_parts("a_half")
        assert parts == [("a", "DT", "a"), ("half", "NN", "half")]

    def test_unknown_unit_returns_none(self, fixer: Fixer) -> None:
        assert fixer._measure_parts("50_frobnitzes") is None

    def test_single_part_returns_none(self, fixer: Fixer) -> None:
        assert fixer._measure_parts("hello") is None


class TestSplitWord:
    """Word splitting with wid shifts and concept relinking."""

    def test_split_shifts_and_relinks(self, fixer: Fixer) -> None:
        add_sentence(fixer, 1, "It costs 50 % now .",
                     [("It", "PRP"), ("costs", "VBZ"), ("50_%", "Zp"),
                      ("now", "RB"), (".", ".")])
        fixer.conn.execute(
            "INSERT INTO concept (sid, cid, clemma, tag) "
            "VALUES (1, 0, '50 %', 'x')")
        fixer.conn.execute(
            "INSERT INTO cwl (sid, wid, cid) VALUES (1, 2, 0)")
        fixer.conn.execute(
            "INSERT INTO cwl (sid, wid, cid) VALUES (1, 3, 99)")

        fixer.split_word(1, 2, fixer._measure_parts("50_%"))

        words = [r[1] for r in fixer.sent_words(1)]
        assert words == ["It", "costs", "50", "%", "now", "."]
        # trailing cwl shifted, split token linked to both parts
        links = fixer.conn.execute(
            "SELECT wid, cid FROM cwl ORDER BY wid").fetchall()
        assert (4, 99) in links
        assert (2, 0) in links and (3, 0) in links

    def test_no_duplicate_wids_after_split(self, fixer: Fixer) -> None:
        add_sentence(fixer, 2, "a bit more",
                     [("a_bit", "Zu"), ("more", "RBR")])
        fixer.split_word(2, 0, fixer._measure_parts("a_bit"))
        dups = fixer.conn.execute(
            "SELECT COUNT(*) FROM (SELECT sid, wid FROM word "
            "GROUP BY sid, wid HAVING COUNT(*) > 1)").fetchone()[0]
        assert dups == 0


class TestQuoteFixes:
    """Open/close quote disambiguation."""

    def test_closing_quote_after_word(self, fixer: Fixer) -> None:
        add_sentence(fixer, 3, 'He said "yes" loudly.',
                     [("He", "PRP"), ("said", "VBD"), ('"', "Fe"),
                      ("yes", "UH"), ('"', "Fe"), ("loudly", "RB"),
                      (".", ".")])
        fixer.quote_fixes()
        poses = [r[2] for r in fixer.sent_words(3)]
        assert poses[2] == "“"
        assert poses[4] == "”"

    def test_possessive_apostrophe(self, fixer: Fixer) -> None:
        add_sentence(fixer, 4, "the boys' school",
                     [("the", "DT"), ("boys", "NNS"), ("'", "Fe"),
                      ("school", "NN")])
        fixer.quote_fixes()
        assert fixer.sent_words(4)[2][2] == "POS"

    def test_decade_to_nn(self, fixer: Fixer) -> None:
        add_sentence(fixer, 5, "back in the '90s music",
                     [("back", "RB"), ("in", "IN"), ("the", "DT"),
                      ("'90s", "Fe"), ("music", "NN")])
        fixer.quote_fixes()
        assert fixer.sent_words(5)[3][2] == "NN"


class TestVax:
    """Auxiliary VAX retagging."""

    def test_vax_table_covers_forms(self) -> None:
        assert VAX_POS["was"] == "VBD"
        assert VAX_POS["'ve"] == "VBP"

    def test_vax_suffix(self, fixer: Fixer) -> None:
        add_sentence(fixer, 6, "He was going",
                     [("He", "PRP"), ("was", "VAX"), ("going", "VBG")])
        fixer.vax_fixes()
        assert fixer.sent_words(6)[1][2] == "VBD-VAX"

    def test_unknown_vax_is_skipped(self, fixer: Fixer) -> None:
        add_sentence(fixer, 7, "He gruntled",
                     [("He", "PRP"), ("gruntled", "VAX")])
        fixer.vax_fixes()
        assert fixer.sent_words(7)[1][2] == "VAX"
        assert any("unknown VAX" in line for line in fixer.report)


class TestConsistency:
    """Tokenisation-versus-text checking."""

    def test_tokens_match_sent(self, fixer: Fixer) -> None:
        assert fixer.tokens_match_sent(
            'He said "hi"', ["He", "said", "``", "hi", "''"])
        assert not fixer.tokens_match_sent(
            "He said hi", ["He", "said", "bye"])

    def test_tab_repair(self, fixer: Fixer) -> None:
        add_sentence(fixer, 8, "one\ttwo", [("one", "CD"), ("two", "CD")])
        broken = fixer.consistency_repair()
        assert 8 not in broken
        text = fixer.conn.execute(
            "SELECT sent FROM sent WHERE sid = 8").fetchone()[0]
        assert "\t" not in text


class TestClemmaSync:
    """Capitalisation synchronisation between clemma and lemmas."""

    def test_capitalise_lemma_from_clemma(self, fixer: Fixer) -> None:
        add_sentence(fixer, 9, "Singapore is nice",
                     [("Singapore", "NNP"), ("is", "VBZ"), ("nice", "JJ")])
        fixer.conn.execute(
            "UPDATE word SET lemma = 'singapore' WHERE sid = 9 AND wid = 0")
        fixer.conn.execute(
            "INSERT INTO concept (sid, cid, clemma, tag) "
            "VALUES (9, 0, 'Singapore', '08921392-n')")
        fixer.conn.execute(
            "INSERT INTO cwl (sid, wid, cid) VALUES (9, 0, 0)")
        fixer.clemma_case_sync()
        lemma = fixer.conn.execute(
            "SELECT lemma FROM word WHERE sid = 9 AND wid = 0").fetchone()[0]
        assert lemma == "Singapore"

    def test_unrelated_mismatch_untouched(self, fixer: Fixer) -> None:
        add_sentence(fixer, 10, "dogs bark", [("dogs", "NNS"), ("bark", "VBP")])
        fixer.conn.execute(
            "INSERT INTO concept (sid, cid, clemma, tag) "
            "VALUES (10, 0, 'hound', '02084071-n')")
        fixer.conn.execute(
            "INSERT INTO cwl (sid, wid, cid) VALUES (10, 0, 0)")
        fixer.clemma_case_sync()
        row = fixer.conn.execute(
            "SELECT clemma FROM concept WHERE sid = 10").fetchone()
        assert row[0] == "hound"
