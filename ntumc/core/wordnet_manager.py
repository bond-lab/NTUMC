import sqlite3
from typing import Optional, List, Tuple

class WordNetManager:
    """
    Manager for WordNet database access.

    This class handles connection creation, querying, and cleanup for
    WordNet databases used in the NTUMC tagger.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish a connection to the WordNet database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)

    def close(self) -> None:
        """Close the connection to the WordNet database."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def query_synsets(self, lemma: str, pos: Optional[str] = None) -> List[Tuple]:
        """
        Query synsets for a given lemma and optional part of speech.

        Args:
            lemma (str): The lemma to query.
            pos (Optional[str]): The part of speech to filter by.

        Returns:
            List[Tuple]: A list of synsets matching the query.
        """
        self.connect()
        cursor = self.conn.cursor()
        query = "SELECT * FROM synsets WHERE lemma = ?"
        params = [lemma]
        if pos:
            query += " AND pos = ?"
            params.append(pos)
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        return results
