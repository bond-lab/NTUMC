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
    data = [
        ('7855', 'a', 'happy', '01148283-a', 1, 37, 'test', 1.0),
        ('22320', 'r', 'fast', '00086000-r', 1, 16, 'test', 1.0),
        ('31633', 'v', 'code', '00994076-v', 2, 0, 'test', 1.0),
        ('50064', 'n', 'newt', '01630284-n', 1, 0, 'test', 1.0),
        ('88125', 'n', 'code', '06353934-n', 2, 1, 'test', 1.0),
        ('1007653', 'x', 'fuck', '76000004-x', 1, 0, 'test', 1.0),
    ]

    for lexid, pos, lemma, synset_id, rank, freq, src, confidence in data:
        cursor.execute("INSERT INTO synset (synset, pos, name, src, usr) VALUES (?, ?, ?, ?, ?)",
                       (synset_id, pos, lemma, src, 'test_user'))
        cursor.execute("INSERT INTO word (lang, lemma, pos, usr) VALUES (?, ?, ?, ?)", ('eng', lemma, pos, 'test_user'))
        wordid = cursor.lastrowid
        cursor.execute("INSERT INTO sense (synset, wordid, lang, rank, lexid, freq, src, confidence, usr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (synset_id, wordid, 'eng', rank, None, freq, src, confidence, 'test_user'))

    conn.commit()
    conn.close()

if __name__ == "__main__":
    db_path = Path(__file__).parent / "wn_test.db"
    create_test_wordnet_db(db_path)
    print(f"Test WordNet database created at {db_path}")
