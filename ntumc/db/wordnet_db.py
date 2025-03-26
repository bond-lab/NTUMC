import sqlite3
from typing import Optional, List, Tuple
from ntumc.core.logging_setup import log_function_call
import logging

class WordNetManager:
    """
    Manager for WordNet database access.

    This class handles connection creation, querying, and cleanup for
    WordNet databases used in the NTUMC tagger.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self.logger = logging.getLogger(__name__)

    def connect(self) -> None:
        """Establish a connection to the WordNet database."""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.logger.debug(f"Established new database connection to {self.db_path}")

    def close(self) -> None:
        """Close the connection to the WordNet database."""
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    @log_function_call
    def Senses(self, lang: str, lemma: Optional[str] = None,
               pos: Optional[str] = None) -> List[Tuple]:
        """
        Query synsets for a given lemma and optional part of speech.

        Args:
            lang (str): The language
            lemma (Optional[str]): The lemma to query.
            pos (Optional[str]): The part of speech to filter by.

        Returns:
            List[Tuple]: A list of synsets matching the query.
        """
        self.connect()
        cursor = self.conn.cursor()
        query = """select lemma, synset from word 
                 left join sense on word.wordid = sense.wordid 
                 where sense.lang = ?"""
        params = [lang]
        if lemma:
            query += " AND lemma = ?"
            params.append(lemma)
        if pos:
            query += " AND word.pos = ?"
            params.append(pos)
        cursor.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        self.logger.info(f"Senses query completed: lang={lang}, lemma={lemma}, pos={pos}, results={len(results)}")
        return results

  
