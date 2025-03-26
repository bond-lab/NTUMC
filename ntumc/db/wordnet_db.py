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
    def delete_language_entries(self, lang: str) -> None:
        """Delete all entries for a given language."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM word WHERE lang = ?", (lang,))
            cursor.execute("DELETE FROM sense WHERE lang = ?", (lang,))
            cursor.execute("DELETE FROM synset_def WHERE lang = ?", (lang,))
            cursor.execute("DELETE FROM synset_ex WHERE lang = ?", (lang,))
            self.conn.commit()
            self.logger.info(f"Deleted all entries for language: {lang}")
        except sqlite3.Error as e:
            self.conn.rollback()
            self.logger.error(f"Error deleting language entries: {str(e)}")
            raise

    @log_function_call
    def insert_word(self, lang: str, word: str, pos: str) -> int:
        """Insert a new word entry and return its wordid."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO word(wordid, lang, lemma, pron, pos) VALUES (?,?,?,?,?)",
                (None, lang, word, None, pos)
            )
            wordid = cursor.lastrowid
            self.conn.commit()
            self.logger.debug(f"Inserted word: {word} ({pos}) for {lang}")
            return wordid
        except sqlite3.Error as e:
            self.conn.rollback()
            self.logger.error(f"Error inserting word: {str(e)}")
            raise

    @log_function_call
    def insert_sense(self, synset: str, wordid: int, lang: str, projectname: str) -> None:
        """Insert a new sense entry."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """INSERT INTO sense(synset, wordid, lang, 
                                   rank, lexid, freq, src, confidence) 
                        VALUES (?,?,?,?,?,?,?,?)""",
                (synset, wordid, lang, None, None, None, projectname, 1.0)
            )
            self.conn.commit()
            self.logger.debug(f"Inserted sense: {synset} for wordid {wordid}")
        except sqlite3.Error as e:
            self.conn.rollback()
            self.logger.error(f"Error inserting sense: {str(e)}")
            raise

    @log_function_call
    def update_synset_def(self, synset: str, lang: str, definition: str, sid: str) -> None:
        """Update or insert a synset definition."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT synset, lang, def, sid 
                   FROM synset_def WHERE synset = ? AND sid = ? AND lang = ?""",
                (synset, sid, lang)
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE synset_def SET def = ? WHERE synset = ? AND sid = ? AND lang = ?",
                    (definition, synset, sid, lang)
                )
            else:
                cursor.execute(
                    "INSERT INTO synset_def(synset, lang, def, sid) VALUES (?,?,?,?)",
                    (synset, lang, sid, definition)
                )
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            self.logger.error(f"Error updating synset definition: {str(e)}")
            raise

    @log_function_call
    def update_synset_ex(self, synset: str, lang: str, example: str, sid: str) -> None:
        """Update or insert a synset example."""
        self.connect()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT synset, lang, def, sid 
                   FROM synset_ex WHERE synset = ? AND sid = ? AND lang = ?""",
                (synset, sid, lang)
            )
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE synset_ex SET def = ? WHERE synset = ? AND sid = ? AND lang = ?",
                    (example, synset, sid, lang)
                )
            else:
                cursor.execute(
                    "INSERT INTO synset_ex(synset, lang, def, sid) VALUES (?,?,?,?)",
                    (synset, lang, sid, example)
                )
            self.conn.commit()
        except sqlite3.Error as e:
            self.conn.rollback()
            self.logger.error(f"Error updating synset example: {str(e)}")
            raise

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

  
