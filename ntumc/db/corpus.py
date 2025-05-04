"""
Corpus interface for NTUMC.

Provides access to documents, sentences, words, and concepts from the corpus database.
"""

import json
from typing import List, Dict, Any, Optional
from ntumc.db.db_manager import DatabaseManager

class Corpus:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_docid_by_docname(self, doc: str) -> Optional[int]:
        """
        Look up docid by doc name.
        """
        with DatabaseManager(self.db_path) as db:
            row = db.fetch_one("SELECT docid FROM doc WHERE doc = ?", (doc,))
            if row:
                return row["docid"]
            return None

    def get_doc(self, docid: int) -> Optional[Dict[str, Any]]:
        """
        Get a document and all its sentences, words, and concepts.
        """
        with DatabaseManager(self.db_path) as db:
            doc = db.fetch_one(
                "SELECT docid, doc, title, subtitle, corpusID FROM doc WHERE docid = ?", (docid,)
            )
            if not doc:
                return None

            # Get all sids for this doc
            sids = [row["sid"] for row in db.fetch_all(
                "SELECT sid FROM sent WHERE docID = ? ORDER BY sid", (docid,)
            )]
            if not sids:
                doc_dict = dict(doc)
                doc_dict["sentences"] = []
                return doc_dict

            min_sid, max_sid = min(sids), max(sids)

            # Bulk fetch words and concepts for all sids in this doc
            words_by_sid = self.get_words_range(min_sid, max_sid)
            concepts_by_sid = self.get_concepts_range(min_sid, max_sid, db=db)

            # Get all sentences
            sents = db.fetch_all(
                "SELECT sid, sent, comment FROM sent WHERE docID = ? ORDER BY sid", (docid,)
            )
            result = []
            for sent in sents:
                sid = sent["sid"]
                stype_row = db.fetch_one(
                    "SELECT stype, comment FROM stype WHERE sid = ?", (sid,)
                )
                stype = stype_row["stype"] if stype_row else None
                stype_comment = stype_row["comment"] if stype_row else None
                sent_dict = {
                    "sid": sid,
                    "text": sent["sent"],
                    "comment": sent["comment"],
                    "stype": stype,
                    "stype_comment": stype_comment,
                    "words": words_by_sid.get(sid, []),
                    "concepts": concepts_by_sid.get(sid, []),
                }
                result.append(sent_dict)

            doc_dict = dict(doc)
            doc_dict["sentences"] = result
            return doc_dict

    def get_sids(self, min_sid: int, max_sid: int, threshold: int) -> List[int]:
        """
        Get sentence IDs with additional 'threshold' sentences before and after,
        ensuring all sentences have the same docid.

        Args:
            min_sid (int): The minimum sentence ID.
            max_sid (int): The maximum sentence ID.
            threshold (int): The number of additional sentences to include before and after.

        Returns:
            List[int]: A list of sentence IDs.
        """
        with DatabaseManager(self.db_path) as db:
            # Get the docid for the given range
            docid_row = db.fetch_one("SELECT docID FROM sent WHERE sid = ?", (min_sid,))
            if not docid_row:
                return []

            docid = docid_row["docID"]

            # Fetch sids with the same docid
            sids = db.fetch_all(
                "SELECT sid FROM sent WHERE docID = ? AND sid BETWEEN ? AND ? ORDER BY sid",
                (docid, min_sid - threshold, max_sid + threshold)
            )
            return [row["sid"] for row in sids]

    def get_sentences(self, min_sid: int, max_sid: int) -> List[Dict[str, Any]]:
        """
        Get sentences and their associated words and concepts for a range of sids.

        Args:
            min_sid (int): The minimum sentence ID.
            max_sid (int): The maximum sentence ID.

        Returns:
            List[Dict[str, Any]]: A list of sentence dictionaries with words and concepts.
        """
        with DatabaseManager(self.db_path) as db:
            # Bulk fetch words and concepts for all sids in this range
            words_by_sid = self.get_words_range(min_sid, max_sid)
            concepts_by_sid = self.get_concepts_range(min_sid, max_sid, db=db)

            # Get all sentences
            sents = db.fetch_all(
                "SELECT sid, sent, comment FROM sent WHERE sid BETWEEN ? AND ? ORDER BY sid", (min_sid, max_sid)
            )
            result = []
            for sent in sents:
                sid = sent["sid"]
                stype_row = db.fetch_one(
                    "SELECT stype, comment FROM stype WHERE sid = ?", (sid,)
                )
                stype = stype_row["stype"] if stype_row else None
                stype_comment = stype_row["comment"] if stype_row else None
                sent_dict = {
                    "sid": sid,
                    "text": sent["sent"],
                    "comment": sent["comment"],
                    "stype": stype,
                    "stype_comment": stype_comment,
                    "words": words_by_sid.get(sid, []),
                    "concepts": concepts_by_sid.get(sid, []),
                }
                result.append(sent_dict)
            return result

    def get_words_range(self, min_sid: int, max_sid: int) -> Dict[int, List[Dict[str, Any]]]:
        """
        Get all words for a range of sids, returned as a dict mapping sid to list of words.
        sid is omitted from each word dict (since it's redundant in this context).
        Null values are omitted from the output.
        """
        with DatabaseManager(self.db_path) as db:
            words = db.fetch_all(
                "SELECT sid, wid, word, pos, lemma, comment FROM word WHERE sid BETWEEN ? AND ? ORDER BY sid, wid",
                (min_sid, max_sid)
            )
            words_by_sid = {}
            for w in words:
                sid = w["sid"]
                # Remove 'sid' and any null values
                word_dict = {k: w[k] for k in w.keys() if k != "sid" and w[k] is not None}
                words_by_sid.setdefault(sid, []).append(word_dict)
            return words_by_sid

    def get_concepts_range(self, min_sid: int, max_sid: int, db=None) -> Dict[int, List[Dict[str, Any]]]:
        """
        Get all concepts for a range of sids, including wids and sentiment, as a dict mapping sid to list of concepts.
        sid is omitted from each concept dict (since it's redundant in this context).
        Null values are omitted from the output.
        """
        # Use the provided db connection if available, else open a new one
        close_db = False
        if db is None:
            db = DatabaseManager(self.db_path)
            db.__enter__()
            close_db = True
        try:
            concepts = db.fetch_all(
                "SELECT sid, cid, clemma, tag, comment FROM concept WHERE sid BETWEEN ? AND ? ORDER BY sid, cid",
                (min_sid, max_sid)
            )
            # Pre-fetch all cwl and sentiment for these sids/cids
            cids_by_sid = [(c["sid"], c["cid"]) for c in concepts]
            wids_map = {}
            sentiment_map = {}

            if cids_by_sid:
                cwl_rows = db.fetch_all(
                    f"SELECT sid, cid, wid FROM cwl WHERE sid BETWEEN ? AND ? ORDER BY sid, cid, wid",
                    (min_sid, max_sid)
                )
                for row in cwl_rows:
                    key = (row["sid"], row["cid"])
                    wids_map.setdefault(key, []).append(row["wid"])

                sentiment_rows = db.fetch_all(
                    f"SELECT sid, cid, score FROM sentiment WHERE sid BETWEEN ? AND ?",
                    (min_sid, max_sid)
                )
                for row in sentiment_rows:
                    key = (row["sid"], row["cid"])
                    sentiment_map[key] = row["score"]

            concepts_by_sid = {}
            for c in concepts:
                sid = c["sid"]
                cid = c["cid"]
                key = (sid, cid)
                # Remove 'sid' and any null values
                concept_dict = {k: c[k] for k in c.keys() if k != "sid" and c[k] is not None}
                wids = wids_map.get(key, [])
                if wids:
                    concept_dict["wids"] = wids
                sentiment = sentiment_map.get(key)
                if sentiment is not None:
                    concept_dict["sentiment"] = sentiment
                concepts_by_sid.setdefault(sid, []).append(concept_dict)
            return concepts_by_sid
        finally:
            if close_db:
                db.__exit__(None, None, None)

    # The old per-sentence methods are kept for compatibility, but now use the range methods for efficiency
    def get_words(self, sid: int) -> List[Dict[str, Any]]:
        """
        Get all words for a sentence.
        sid is omitted from each word dict (since it's redundant in this context).
        Null values are omitted from the output.
        """
        words_by_sid = self.get_words_range(sid, sid)
        return words_by_sid.get(sid, [])

    def get_concepts(self, sid: int) -> List[Dict[str, Any]]:
        """
        Get all concepts for a sentence, including wids, sentiment, etc.
        sid is omitted from each concept dict (since it's redundant in this context).
        Null values are omitted from the output.
        """
        concepts_by_sid = self.get_concepts_range(sid, sid)
        return concepts_by_sid.get(sid, [])

    def dump_doc_json(self, docid: int, out: str = None) -> str:
        """
        Dump a document and its data as JSON.
        If 'out' is provided, write the JSON to that file and return the path.
        Otherwise, return the JSON string.
        """
        doc = self.get_doc(docid)
        json_str = json.dumps(doc, ensure_ascii=False, indent=2)
        if out:
            with open(out, "w", encoding="utf-8") as f:
                f.write(json_str)
            return out
        return json_str

    # Optionally, add YAML support if needed
    def dump_doc_yaml(self, docid: int) -> str:
        """
        Dump a document and its data as YAML.
        """
        try:
            import yaml
        except ImportError:
            raise RuntimeError("PyYAML is not installed")
        doc = self.get_doc(docid)
        return yaml.dump(doc, allow_unicode=True, sort_keys=False)


    def update_concept_tag(self, sid: int, cid: int, tag: str, usr: Optional[str] = None) -> None:
        """
        Update the tag for a concept in the database.

        Args:
            sid (int): The sentence ID.
            cid (int): The concept ID.
            tag (str): The tag to update.
        """
        with DatabaseManager(self.db_path) as db:
            db.execute(
                "UPDATE concept SET tag = ?, usrname = ? WHERE sid = ? AND cid = ?",
                (tag, usr, sid, cid)
            )
            db.conn.commit()

            
    def update_sentiment_score(self, sid: int, cid: int, score: float, usr: Optional[str] = None) -> None:
        """
        Update the sentiment score for a concept in the database.

        Args:
            sid (int): The sentence ID.
            cid (int): The concept ID.
            score (float): The score to update.
        """
        print("Updating sentiment", score, usr, sid, cid)
        with DatabaseManager(self.db_path) as db:
            db.execute(
                "UPDATE sentiment SET score = ?, username = ? WHERE sid = ? AND cid = ?",
                (score, usr, sid, cid)
            )
            db.conn.commit()
      
    def commit_and_close(self) -> None:
        """
        Commit any pending transactions and close the database connection.
        """
        with DatabaseManager(self.db_path) as db:
            db.conn.commit()
            db.conn.close()
