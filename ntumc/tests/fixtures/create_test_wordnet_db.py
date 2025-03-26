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
