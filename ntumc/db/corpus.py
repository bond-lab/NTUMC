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

            doc_dict = dict(doc)
            doc_dict["sentences"] = self.get_sentences(docid)
            return doc_dict

    def get_sentences(self, docid: int) -> List[Dict[str, Any]]:
        """
        Get all sentences for a document, including stype and comments.
        """
        with DatabaseManager(self.db_path) as db:
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
                    "words": self.get_words(sid),
                    "concepts": self.get_concepts(sid),
                }
                result.append(sent_dict)
            return result

    def get_words(self, sid: int) -> List[Dict[str, Any]]:
        """
        Get all words for a sentence.
        """
        with DatabaseManager(self.db_path) as db:
            words = db.fetch_all(
                "SELECT sid, wid, word, pos, lemma, comment FROM word WHERE sid = ? ORDER BY wid", (sid,)
            )
            return [dict(w) for w in words]

    def get_concepts(self, sid: int) -> List[Dict[str, Any]]:
        """
        Get all concepts for a sentence, including wids, sentiment, etc.
        """
        with DatabaseManager(self.db_path) as db:
            concepts = db.fetch_all(
                "SELECT sid, cid, clemma, tag, comment FROM concept WHERE sid = ? ORDER BY cid", (sid,)
            )
            result = []
            for c in concepts:
                cid = c["cid"]
                # Get wids from cwl
                wids = [
                    row["wid"] for row in db.fetch_all(
                        "SELECT wid FROM cwl WHERE sid = ? AND cid = ? ORDER BY wid", (sid, cid)
                    )
                ]
                # Get sentiment
                sentiment_row = db.fetch_one(
                    "SELECT score FROM sentiment WHERE sid = ? AND cid = ?", (sid, cid)
                )
                sentiment = sentiment_row["score"] if sentiment_row else None
                concept_dict = dict(c)
                concept_dict["wids"] = wids
                concept_dict["sentiment"] = sentiment
                result.append(concept_dict)
            return result

    def dump_doc_json(self, docid: int) -> str:
        """
        Dump a document and its data as JSON.
        """
        doc = self.get_doc(docid)
        return json.dumps(doc, ensure_ascii=False, indent=2)

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
