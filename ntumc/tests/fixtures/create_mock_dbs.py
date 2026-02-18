#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create mock databases for testing the DatabaseManager.

This script creates mock SQLite databases for the WordNet and corpus
databases used in testing. It generates a minimal schema matching the
real databases but with a small amount of test data.
"""

import os
import sqlite3
import argparse
from pathlib import Path

def create_wordnet_db(output_path):
    """Create a mock WordNet database with minimal schema."""
    print(f"Creating mock WordNet database at {output_path}")
    
    conn = sqlite3.connect(output_path)
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
    INSERT INTO word (wordid, lemma) VALUES (3, 'run');
    INSERT INTO word (wordid, lemma) VALUES (4, 'book');
    INSERT INTO word (wordid, lemma) VALUES (5, 'fast');
    
    INSERT INTO sense (synset, wordid, lang) VALUES ('n12345678', 1, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('n87654321', 2, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('v12345678', 3, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('n23456789', 4, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('v23456789', 4, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('a12345678', 5, 'eng');
    INSERT INTO sense (synset, wordid, lang) VALUES ('r12345678', 5, 'eng');
    ''')
    conn.commit()
    conn.close()
    print("Mock WordNet database created successfully.")

def create_corpus_db(output_path):
    """Create a mock corpus database with minimal schema."""
    print(f"Creating mock corpus database at {output_path}")
    
    conn = sqlite3.connect(output_path)
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
        FOREIGN KEY(sid) REFERENCES sent(sid),
        FOREIGN KEY(cid) REFERENCES concept(cid)
    );
    
    -- Insert some test data
    INSERT INTO meta (title, license, lang, version) 
    VALUES ('Mock Corpus', 'CC-BY', 'eng', '1.0');
    
    INSERT INTO corpus (corpusID, corpus, title, language) 
    VALUES (1, 'mock_corpus', 'Mock Corpus', 'eng');
    
    INSERT INTO doc (docid, doc, title, corpusID) 
    VALUES (1, 'doc1', 'Test Document 1', 1);
    INSERT INTO doc (docid, doc, title, corpusID) 
    VALUES (2, 'doc2', 'Test Document 2', 1);
    
    INSERT INTO sent (sid, docID, sent) 
    VALUES (1, 1, 'This is a test sentence.');
    INSERT INTO sent (sid, docID, sent) 
    VALUES (2, 1, 'The quick brown fox jumps over the lazy dog.');
    INSERT INTO sent (sid, docID, sent) 
    VALUES (3, 2, 'Another example sentence for testing.');
    
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 1, 'This', 'DT', 'this');
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 2, 'is', 'VBZ', 'be');
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 3, 'a', 'DT', 'a');
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 4, 'test', 'NN', 'test');
    INSERT INTO word (sid, wid, word, pos, lemma) 
    VALUES (1, 5, 'sentence', 'NN', 'sentence');
    
    INSERT INTO concept (sid, cid, clemma, tag, tags) 
    VALUES (1, 1, 'be', 'v', 'v00007000');
    INSERT INTO concept (sid, cid, clemma, tag, tags) 
    VALUES (1, 2, 'test', 'n', 'n03459272');
    
    INSERT INTO cwl (sid, wid, cid) 
    VALUES (1, 2, 1);
    INSERT INTO cwl (sid, wid, cid) 
    VALUES (1, 4, 2);
    ''')
    conn.commit()
    conn.close()
    print("Mock corpus database created successfully.")

def main():
    parser = argparse.ArgumentParser(description='Create mock databases for testing')
    parser.add_argument('--wordnet', help='Path for WordNet database', default='mock_wordnet.db')
    parser.add_argument('--corpus', help='Path for corpus database', default='mock_corpus.db')
    args = parser.parse_args()
    
    create_wordnet_db(args.wordnet)
    create_corpus_db(args.corpus)

if __name__ == '__main__':
    main()
