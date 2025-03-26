import sqlite3
from pathlib import Path

def create_test_wordnet_db(db_path: str):
    """Create a small test WordNet database with minimally 5 synsets."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS word (
            wordid INTEGER PRIMARY KEY AUTOINCREMENT,
            lang TEXT NOT NULL,
            lemma TEXT NOT NULL,
            pron TEXT,
            pos TEXT NOT NULL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sense (
            synset TEXT NOT NULL,
            wordid INTEGER NOT NULL,
            lang TEXT NOT NULL,
            rank INTEGER,
            lexid INTEGER,
            freq INTEGER,
            src TEXT,
            confidence REAL,
            PRIMARY KEY (synset, wordid, lang)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS synset_def (
            synset TEXT NOT NULL,
            lang TEXT NOT NULL,
            def TEXT NOT NULL,
            sid TEXT NOT NULL,
            PRIMARY KEY (synset, lang, sid)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS synset_ex (
            synset TEXT NOT NULL,
            lang TEXT NOT NULL,
            def TEXT NOT NULL,
            sid TEXT NOT NULL,
            PRIMARY KEY (synset, lang, sid)
        )
    ''')

    # Insert test data
    test_data = [
        ('n0001', 'eng', 'dog', 'n'),
        ('v0001', 'eng', 'run', 'v'),
        ('a0001', 'eng', 'happy', 'a'),
        ('r0001', 'eng', 'quickly', 'r'),
        ('s0001', 'eng', 'blue', 's')
    ]

    for synset, lang, lemma, pos in test_data:
        cursor.execute("INSERT INTO word (lang, lemma, pos) VALUES (?, ?, ?)", (lang, lemma, pos))
        wordid = cursor.lastrowid
        cursor.execute("INSERT INTO sense (synset, wordid, lang, src, confidence) VALUES (?, ?, ?, ?, ?)",
                       (synset, wordid, lang, 'test_project', 1.0))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = Path(__file__).parent / "test_wn.db"
    create_test_wordnet_db(db_path)
    print(f"Test WordNet database created at {db_path}")
