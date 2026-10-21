"""Tests for fix_pronoun_tags.py (either/哪 retags after fixwn.py)."""

import sqlite3

import pytest
from fix_pronoun_tags import BOTH, EITHER_UNIV, WHICH, retag

SYNSETS = {BOTH, EITHER_UNIV, WHICH, "77000079-a"}


@pytest.fixture
def conn() -> sqlite3.Connection:
    """In-memory corpus database with one either token and one both token."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, PRIMARY KEY (sid, cid));
        INSERT INTO concept VALUES (13629, 18, 'either', '77000076-a');
        INSERT INTO concept VALUES (11341, 12, 'either', '77000076-a');
        INSERT INTO concept VALUES (13629, 1, 'both', '77000076-a');
        """
    )
    return conn


def tag(conn: sqlite3.Connection, sid: int, cid: int) -> str:
    """Return the tag of one concept."""
    return conn.execute("SELECT tag FROM concept WHERE sid = ? AND cid = ?",
                        (sid, cid)).fetchone()[0]


def test_retags_listed_tokens(conn: sqlite3.Connection) -> None:
    """Universal either and either...or are retagged; both is untouched."""
    counts = retag(conn, "eng", SYNSETS, dry_run=False)

    assert tag(conn, 13629, 18) == EITHER_UNIV
    assert tag(conn, 11341, 12) == "x"
    assert tag(conn, 13629, 1) == BOTH
    assert counts["retagged"] == 2


def test_dry_run_changes_nothing(conn: sqlite3.Connection) -> None:
    """A dry run counts the changes but leaves the tags alone."""
    counts = retag(conn, "eng", SYNSETS, dry_run=True)

    assert tag(conn, 13629, 18) == BOTH
    assert counts["retagged"] == 2


def test_second_run_is_idempotent(conn: sqlite3.Connection) -> None:
    """Re-running finds the tokens already done."""
    retag(conn, "eng", SYNSETS, dry_run=False)

    counts = retag(conn, "eng", SYNSETS, dry_run=False)

    assert counts["retagged"] == 0
    assert counts["already"] == 2


def test_skips_changed_or_moved_tokens(conn: sqlite3.Connection) -> None:
    """A token with a different tag or lemma at that position is skipped."""
    conn.execute("UPDATE concept SET tag = '00024893-r' "
                 "WHERE sid = 13629 AND cid = 18")
    conn.execute("UPDATE concept SET clemma = 'or' "
                 "WHERE sid = 11341 AND cid = 12")

    counts = retag(conn, "eng", SYNSETS, dry_run=False)

    assert tag(conn, 13629, 18) == "00024893-r"
    assert tag(conn, 11341, 12) == BOTH
    assert counts["retagged"] == 0


def test_skips_missing_synset(conn: sqlite3.Connection) -> None:
    """A target synset absent from the wordnet is not applied."""
    counts = retag(conn, "eng", {BOTH}, dry_run=False)

    assert tag(conn, 13629, 18) == BOTH
    assert tag(conn, 11341, 12) == "x"
    assert counts["retagged"] == 1
