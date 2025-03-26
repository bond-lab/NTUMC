import sqlite3
from pathlib import Path

def create_test_wordnet_db(db_path: str):
    """Create a small test WordNet database with minimally 5 synsets."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Read and execute the schema from the SQL file
    with open('data/wn-ntumc.sql', 'r') as schema_file:
        schema_sql = schema_file.read()
    cursor.executescript(schema_sql)

    # Insert test data
    synsets = [
        ('n0001', 'n', 'dog'),
        ('v0001', 'v', 'run'),
        ('a0001', 'a', 'happy'),
        ('r0001', 'r', 'quickly'),
        ('s0001', 's', 'blue'),
        ('v31633', 'v', 'code'),
        ('n88125', 'n', 'code'),
        ('n50064', 'n', 'newt'),
        ('r22320', 'r', 'fast'),
        ('a7855', 'a', 'happy'),
        ('x1007653', 'x', 'fuck')
    ]

    for synset, pos, lemma in synsets:
        cursor.execute("INSERT INTO synset (synset, pos, name, src, usr) VALUES (?, ?, ?, ?, ?)",
                       (synset, pos, lemma, 'test_project', 'test_user'))
        cursor.execute("INSERT INTO word (lang, lemma, pos, usr) VALUES (?, ?, ?, ?)", ('eng', lemma, pos, 'test_user'))
        wordid = cursor.lastrowid
        cursor.execute("INSERT INTO sense (synset, wordid, lang, src, confidence) VALUES (?, ?, ?, ?, ?)",
                       (synset, wordid, 'eng', 'test_project', 1.0))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = Path(__file__).parent / "test_wn.db"
    create_test_wordnet_db(db_path)
    print(f"Test WordNet database created at {db_path}")
