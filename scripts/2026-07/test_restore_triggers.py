"""Tests for restore_triggers.py."""

import sqlite3

import pytest
from restore_triggers import load_triggers, misdirected, restore


@pytest.fixture
def conn() -> sqlite3.Connection:
    """Corpus tables and log tables with no triggers."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE word (sid, wid, word, pos, lemma, cfrom, cto, comment,
                           usrname);
        CREATE TABLE word_log (sid_new, sid_old, wid_new, wid_old, word_new,
                               word_old, pos_new, pos_old, lemma_new,
                               lemma_old, cfrom_new, cfrom_old, cto_new,
                               cto_old, comment_new, comment_old, usrname_new,
                               usrname_old, date_update);
        CREATE TABLE sent_log (sid_old);
        """
    )
    return conn


def test_canonical_file_has_all_triggers() -> None:
    """The SQL file defines 14 triggers, none misdirected."""
    triggers = load_triggers()

    assert len(triggers) == 14
    assert not any(misdirected(sql) for sql in triggers.values())


def test_creates_missing_triggers_and_logs(conn: sqlite3.Connection) -> None:
    """Missing word triggers are created and then log a deletion."""
    changes = restore(conn, load_triggers(), dry_run=False)
    conn.execute("INSERT INTO word (sid, wid, word) VALUES (1, 0, 'cat')")
    conn.execute("DELETE FROM word")

    assert "create delete_word_log" in changes
    assert conn.execute("SELECT count(*) FROM word_log").fetchone()[0] == 2


def test_replaces_misdirected_trigger(conn: sqlite3.Connection) -> None:
    """A word trigger writing to sent_log is replaced, so deletes work."""
    conn.execute("CREATE TRIGGER delete_word_log AFTER DELETE ON word BEGIN "
                 "INSERT INTO sent_log (sid_old) VALUES (old.sid); END")

    changes = restore(conn, load_triggers(), dry_run=False)

    assert "replace delete_word_log (wrote to sent_log)" in changes
    assert restore(conn, load_triggers(), dry_run=False) == []


def test_dry_run_changes_nothing(conn: sqlite3.Connection) -> None:
    """A dry run reports changes but creates no triggers."""
    changes = restore(conn, load_triggers(), dry_run=True)

    assert changes
    assert conn.execute("SELECT count(*) FROM sqlite_master "
                        "WHERE type='trigger'").fetchone()[0] == 0
