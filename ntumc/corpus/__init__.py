"""The NTU-MC corpus as Python objects, with database and JSON Lines I/O.

Typical use::

    from ntumc.corpus import Corpus, jsonl, validate

    corpus = Corpus.from_items(jsonl.read("catb.jsonl"))
    eng = corpus.document("eng", "catb")
    for sent in eng:
        for concept in sent.tagged():
            print(concept.clemma, concept.tag, [w.word for w in sent.words_of(concept)])

    for problem in validate(corpus):
        print(problem)

Streaming from the databases::

    from ntumc.corpus import db
    for doc in db.read_documents("build/jpn.db"):
        ...
"""

from . import db, dbwrite, jsonl, xmlio
from .model import (
    GENRES,
    Alignment,
    Chunk,
    Concept,
    ConceptLink,
    Corpus,
    CorpusError,
    CorpusInfo,
    Document,
    Item,
    Sentence,
    SentLink,
    Word,
    WordLink,
)
from .validate import Problem, validate

__all__ = [
    "GENRES",
    "Alignment",
    "Chunk",
    "Concept",
    "ConceptLink",
    "Corpus",
    "CorpusError",
    "CorpusInfo",
    "Document",
    "Item",
    "Problem",
    "SentLink",
    "Sentence",
    "Word",
    "WordLink",
    "db",
    "dbwrite",
    "jsonl",
    "validate",
    "xmlio",
]
