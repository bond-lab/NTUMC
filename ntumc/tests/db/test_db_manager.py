#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for the DatabaseManager class and utilities.
"""

import os
import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from ntumc.db.db_manager import (
    DatabaseManager, 
    check_connection, 
    create_backup, 
    optimize_database,
    get_connection,
    ConnectionError,
    QueryError,
    DatabaseError
)

# Fixtures
# Fixtures
@pytest.fixture
def temp_db_path():
    """Create a temporary database file."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup after test
    if os.path.exists(path):
        os.unlink(path)

@pytest.fixture
def mock_wordnet_db():
    """Create a mock WordNet database with minimal schema."""
    # Create a separate temporary file for WordNet DB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    conn = sqlite3.connect(path)
    
    # Drop tables if they exist
    conn.executescript('''
    DROP TABLE IF EXISTS sense;
    DROP TABLE IF EXISTS word;
    ''')
    
    conn.executescript('''
    CREATE TABLE word (
        wordid INTEGER PRIMARY KEY,
        lemma TEXT
    );
    CREATE TABLE sense (
        synset TEXT,
        wordid INTEGER,
        lang TEXT,
        FOREIGN KEY(wordid) REFERENCES word(wordid)
    );
    
    -- Insert some test data
    INSERT INTO word (wordid, lemma) VALUES (1, 'test');
    INSERT INTO word (wordid, lemma) VALUES (2, 'example');
    INSERT INTO sense (synset, wordid, lang) VALUES ('n12345678', 1, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('v87654321', 2, 'eng');
    ''')
    conn.commit()
    conn.close()
    
    yield path
    
    # Cleanup after test
    if os.path.exists(path):
        os.unlink(path)

@pytest.fixture
def mock_corpus_db():
    """Create a mock corpus database with minimal schema."""
    # Create a separate temporary file for Corpus DB
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    
    conn = sqlite3.connect(path)
    
    # Drop tables if they exist
    conn.executescript('''
    DROP TABLE IF EXISTS cwl;
    DROP TABLE IF EXISTS concept;
    DROP TABLE IF EXISTS word;
    DROP TABLE IF EXISTS sent;
    DROP TABLE IF EXISTS doc;
    DROP TABLE IF EXISTS corpus;
    DROP TABLE IF EXISTS meta;
    ''')
    
    conn.executescript('''
    CREATE TABLE meta (
        title TEXT,
        license TEXT,
        lang TEXT,
        version TEXT,
        master TEXT
    );
    CREATE TABLE corpus (
        corpusID INTEGER PRIMARY KEY,
        corpus TEXT,
        title TEXT,
        language TEXT
    );
    CREATE TABLE doc (
        docid INTEGER PRIMARY KEY,
        doc TEXT,
        title TEXT,
        url TEXT,
        subtitle TEXT,
        corpusID INTEGER,
        FOREIGN KEY (corpusID) REFERENCES corpus(corpusID)
    );
    CREATE TABLE sent (
        sid INTEGER PRIMARY KEY,
        docID INTEGER,
        pid TEXT,
        sent TEXT,
        comment TEXT,
        usrname TEXT,
        FOREIGN KEY(docID) REFERENCES doc(docID)
    );
    CREATE TABLE word (
        sid INTEGER,
        wid INTEGER,
        word TEXT,
        pos TEXT,
        lemma TEXT,
        cfrom INTEGER,
        cto INTEGER,
        comment TEXT,
        usrname TEXT,
        PRIMARY KEY (sid, wid),
        FOREIGN KEY(sid) REFERENCES sent(sid)
    );
    CREATE TABLE concept (
        sid INTEGER,
        cid INTEGER,
        clemma TEXT,
        tag TEXT,
        tags TEXT,
        comment TEXT,
        ntag TEXT,
        usrname TEXT,
        PRIMARY KEY (sid, cid),
        FOREIGN KEY(sid) REFERENCES sent(sid)
    );
    CREATE TABLE cwl (
        sid INTEGER,
        wid INTEGER,
        cid INTEGER,
        usrname TEXT,
        PRIMARY KEY (sid, wid, cid),
        FOREIGN KEY(sid, wid) REFERENCES word(sid, wid),
        FOREIGN KEY(sid, cid) REFERENCES concept(sid, cid)
    );
    
    -- Insert some test data
    INSERT INTO corpus (corpusID, corpus, title, language) 
    VALUES (1, 'test_corpus', 'Test Corpus', 'eng');
    
    INSERT INTO doc (docid, doc, title, corpusID) 
    VALUES (1, 'test_doc', 'Test Document', 1);
    
    INSERT INTO sent (sid, docID, sent) 
    VALUES (1, 1, 'This is a test sentence.');
    
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 1, 'This', 'DT', 'this');
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 2, 'is', 'VBZ', 'be');
    ''')
    conn.commit()
    conn.close()
    
    yield path
    
    # Cleanup after test
    if os.path.exists(path):
        os.unlink(path)
# Basic Connection Tests
class TestDatabaseManager:
    def test_init_valid_db(self, mock_corpus_db):
        """Test initializing with a valid database."""
        db = DatabaseManager(mock_corpus_db)
        assert db.db_path == mock_corpus_db
        assert db.conn is None
        assert db.cursor is None
        assert db.in_transaction is False
    
    def test_init_invalid_db(self):
        """Test initializing with an invalid database path."""
        with pytest.raises(ConnectionError):
            DatabaseManager("/path/to/nonexistent/db.sqlite")
    
    def test_context_manager(self, mock_corpus_db):
        """Test using the manager as a context manager."""
        with DatabaseManager(mock_corpus_db) as db:
            assert db.conn is not None
            assert db.cursor is not None
            assert isinstance(db.conn, sqlite3.Connection)
        
        # Connection should be closed after exiting context
        assert db.conn is None
    
    def test_context_manager_exception(self, mock_corpus_db):
        """Test context manager handles exceptions properly."""
        try:
            with DatabaseManager(mock_corpus_db) as db:
                db.execute("SELECT * FROM nonexistent_table")
                pytest.fail("Should have raised an exception")
        except QueryError:
            pass
        
        # Connection should be closed after exception
        assert db.conn is None
    
    def test_connect_and_close(self, mock_corpus_db):
        """Test explicit connect and close methods."""
        db = DatabaseManager(mock_corpus_db)
        db.connect()
        assert db.conn is not None
        assert db.cursor is not None
        
        db.close()
        assert db.conn is None
        assert db.cursor is None
    
    def test_transaction_management(self, mock_corpus_db):
        """Test transaction management."""
        with DatabaseManager(mock_corpus_db) as db:
            # Begin a transaction
            db.begin_transaction()
            assert db.in_transaction is True
            
            # Execute a query
            db.execute("INSERT INTO word (sid, wid, word, pos, lemma) VALUES (1, 3, 'test', 'NN', 'test')")
            
            # Rollback
            db.rollback()
            assert db.in_transaction is False
            
            # Transaction should have been rolled back
            result = db.fetch_one("SELECT COUNT(*) FROM word WHERE word = 'test'")
            assert result[0] == 0
            
            # Begin another transaction
            db.begin_transaction()
            db.execute("INSERT INTO word (sid, wid, word, pos, lemma) VALUES (1, 3, 'test', 'NN', 'test')")
            
            # Commit
            db.commit()
            assert db.in_transaction is False
            
            # Transaction should have been committed
            result = db.fetch_one("SELECT COUNT(*) FROM word WHERE word = 'test'")
            assert result[0] == 1
    
    def test_query_methods(self, mock_corpus_db):
        """Test various query methods."""
        with DatabaseManager(mock_corpus_db) as db:
            # fetch_one
            result = db.fetch_one("SELECT word FROM word WHERE wid = ?", (1,))
            assert result['word'] == 'This'
            
            # fetch_all
            results = db.fetch_all("SELECT word FROM word ORDER BY wid")
            assert len(results) == 2
            assert results[0]['word'] == 'This'
            assert results[1]['word'] == 'is'
            
            # fetch_dict with key_column
            results = db.fetch_dict("SELECT wid, word FROM word", key_column='wid')
            assert results[1]['word'] == 'This'
            assert results[2]['word'] == 'is'
            
            # fetch_dict without key_column
            results = db.fetch_dict("SELECT wid, word FROM word ORDER BY wid")
            assert len(results) == 2
            assert results[0]['wid'] == 1
            assert results[0]['word'] == 'This'
            
            # Start a transaction before executemany
            db.begin_transaction()
            
            # executemany
            db.executemany(
                "INSERT INTO word (sid, wid, word, pos, lemma) VALUES (?, ?, ?, ?, ?)", 
                [(1, 3, 'a', 'DT', 'a'), (1, 4, 'test', 'NN', 'test')]
            )
            db.commit()
            
            count = db.fetch_one("SELECT COUNT(*) FROM word")[0]
            assert count == 4
            assert count == 4
    
    def test_table_exists(self, mock_corpus_db):
        """Test table_exists method."""
        with DatabaseManager(mock_corpus_db) as db:
            assert db.table_exists('word') is True
            assert db.table_exists('nonexistent') is False


# Database Utility Tests
class TestDatabaseUtilities:
    def test_check_connection_valid(self, mock_corpus_db):
        """Test check_connection with valid database."""
        assert check_connection(mock_corpus_db) is True
    
    def test_check_connection_invalid(self):
        """Test check_connection with invalid database."""
        assert check_connection("/path/to/nonexistent/db.sqlite") is False
    
    def test_create_backup(self, mock_corpus_db, temp_db_path):
        """Test creating a backup."""
        backup_dir = os.path.dirname(temp_db_path)
        backup_path = create_backup(mock_corpus_db, backup_dir)
        
        assert backup_path is not None
        assert os.path.exists(backup_path)
        assert os.path.getsize(backup_path) > 0
    
    def test_create_backup_nonexistent(self):
        """Test creating a backup of nonexistent database."""
        backup_path = create_backup("/path/to/nonexistent/db.sqlite")
        assert backup_path is None
    
    def test_optimize_database(self, mock_corpus_db):
        """Test optimizing database."""
        with sqlite3.connect(mock_corpus_db) as conn:
            assert optimize_database(conn) is True
    
    def test_get_connection_context_manager(self, mock_corpus_db):
        """Test get_connection context manager."""
        with get_connection(mock_corpus_db) as conn:
            assert isinstance(conn, sqlite3.Connection)
            # Execute a simple query
            cursor = conn.execute("SELECT COUNT(*) FROM word")
            assert cursor.fetchone()[0] == 2
        
        # Connection should be closed
        with pytest.raises(Exception):
            conn.execute("SELECT 1")
    
    def test_get_connection_error(self):
        """Test get_connection with invalid path."""
        with pytest.raises(ConnectionError):
            with get_connection("/path/to/nonexistent/db.sqlite"):
                pass


# Example Usage Test
            corpus_db.rollback()
            raise
def test_example_usage(mock_wordnet_db, mock_corpus_db):
    """Test a typical usage scenario."""
    # Connect to WordNet database
    with DatabaseManager(mock_wordnet_db) as wn_db:
        # Query for a lemma
        synsets = wn_db.fetch_all("""
            SELECT sense.synset 
            FROM word 
            JOIN sense ON word.wordid = sense.wordid 
            WHERE word.lemma = ? AND sense.lang = ?
        """, ('test', 'eng'))
        
        assert len(synsets) == 1
        assert synsets[0]['synset'] == 'n12345678'
    
    # Connect to corpus database
    with DatabaseManager(mock_corpus_db) as corpus_db:
        # Begin a transaction
        corpus_db.begin_transaction()
        
        try:
            # Get sentence to tag
            sentence = corpus_db.fetch_one("""
                SELECT s.sid, s.sent, d.docid
                FROM sent s
                JOIN doc d ON s.docID = d.docid
                LIMIT 1
            """)
            
            # Get words in sentence
            words = corpus_db.fetch_all("""
                SELECT wid, word, pos, lemma
                FROM word
                WHERE sid = ?
                ORDER BY wid
            """, (sentence['sid'],))
            
            # We need to insert the concept first (before cwl)
            next_cid = 1
            corpus_db.execute("""
                INSERT INTO concept(sid, cid, clemma, tag, tags)
                VALUES (?, ?, ?, ?, ?)
            """, (sentence['sid'], next_cid, 'be', 'v', 'v01234567'))
            
            # Now we can safely insert into cwl with proper foreign key references
            corpus_db.execute("""
                INSERT INTO cwl(sid, cid, wid)
                VALUES (?, ?, ?)
            """, (sentence['sid'], next_cid, 2))  # Link to 'is'
            
            # Commit transaction
            corpus_db.commit()
            
            # Verify the tag was added
            concept = corpus_db.fetch_one("""
                SELECT * FROM concept WHERE sid = ? AND cid = ?
            """, (sentence['sid'], next_cid))
            
            assert concept is not None
            assert concept['clemma'] == 'be'
            assert concept['tag'] == 'v'
            
        except Exception as e:
            corpus_db.rollback()
            raise
            corpus_db.rollback()
            raise
