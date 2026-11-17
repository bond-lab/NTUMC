"""The NTU-MC corpus as plain Python objects.

A corpus is a set of documents, one language each, plus alignments
between languages.  The classes here mirror the SQLite schema
(``data/ntumc.sql`` and ``data/link.sql``) and the XML format
(``data/ntumc.dtd``); the JSON format is their direct serialisation.

Ids (``sid``, ``wid``, ``cid``, ``xid``) are the database integers:
``sid`` is unique within a language, the others within a sentence.
Links name their two ends as ``(sid, wid)`` and so on, in the ``from``
and ``to`` languages of the alignment.

Field names follow the database columns, with these renamings:
``sent`` is ``text``, ``usrname``/``username`` is ``user``,
``concept.tags`` is ``candidates``, ``concept.ntag`` is ``ne``, and the
``cwl``/``xwl``/``sentiment``/``stype`` tables are folded into the
objects they describe.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import KW_ONLY, dataclass, field

GENRES = ("essay", "fiction", "lexical", "news", "online", "tourism")
META_TAGS = ("e", "w", "x")


class CorpusError(Exception):
    """A problem in the data that stops a reader or writer."""


@dataclass
class Word:
    """One token of a sentence."""

    wid: int
    word: str
    _: KW_ONLY
    lemma: str | None = None
    pos: str | None = None
    cfrom: int | None = None
    cto: int | None = None
    comment: str | None = None
    user: str | None = None


@dataclass
class Concept:
    """A sense-tagged concept covering one or more words."""

    cid: int
    clemma: str
    _: KW_ONLY
    tag: str | None = None
    wids: list[int] = field(default_factory=list)
    ne: str | None = None
    candidates: list[str] = field(default_factory=list)
    sentiment: float | None = None
    sentiment_user: str | None = None
    comment: str | None = None
    user: str | None = None

    @property
    def is_synset(self) -> bool:
        """True if the tag is a wordnet synset id rather than e/w/x or empty."""
        return bool(self.tag) and self.tag not in META_TAGS


@dataclass
class Chunk:
    """A span of words with a sentiment score."""

    xid: int
    _: KW_ONLY
    wids: list[int] = field(default_factory=list)
    score: float | None = None
    comment: str | None = None
    user: str | None = None


@dataclass
class Sentence:
    """A sentence with its words, concepts and chunks."""

    sid: int
    text: str
    _: KW_ONLY
    pid: str | None = None
    stype: str | None = None
    stype_comment: str | None = None
    comment: str | None = None
    user: str | None = None
    words: list[Word] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)

    def word(self, wid: int) -> Word:
        """Return the word with this wid.

        Args:
            wid: word id within the sentence

        Returns:
            The word

        Raises:
            KeyError: if there is no such word
        """
        for w in self.words:
            if w.wid == wid:
                return w
        raise KeyError(f"sentence {self.sid} has no word {wid}")

    def concept(self, cid: int) -> Concept:
        """Return the concept with this cid.

        Args:
            cid: concept id within the sentence

        Returns:
            The concept

        Raises:
            KeyError: if there is no such concept
        """
        for c in self.concepts:
            if c.cid == cid:
                return c
        raise KeyError(f"sentence {self.sid} has no concept {cid}")

    def words_of(self, item: Concept | Chunk) -> list[Word]:
        """Return the words a concept or chunk covers, in wid order.

        Args:
            item: a concept or chunk of this sentence

        Returns:
            Its words; words whose wid is missing are left out
        """
        by_wid = {w.wid: w for w in self.words}
        return [by_wid[w] for w in sorted(item.wids) if w in by_wid]

    def tagged(self) -> list[Concept]:
        """Return the concepts tagged with a synset."""
        return [c for c in self.concepts if c.is_synset]


@dataclass
class Document:
    """A document in one language."""

    docid: int
    doc: str
    language: str
    _: KW_ONLY
    title: str = ""
    subtitle: str | None = None
    url: str | None = None
    collection: str | None = None
    collection_title: str | None = None
    genre: str | None = None
    sentences: list[Sentence] = field(default_factory=list)

    def __iter__(self) -> Iterator[Sentence]:
        return iter(self.sentences)

    def __len__(self) -> int:
        return len(self.sentences)

    def sentence(self, sid: int) -> Sentence:
        """Return the sentence with this sid.

        Args:
            sid: sentence id

        Returns:
            The sentence

        Raises:
            KeyError: if there is no such sentence
        """
        for s in self.sentences:
            if s.sid == sid:
                return s
        raise KeyError(f"document {self.doc} has no sentence {sid}")

    def words(self) -> Iterator[tuple[Sentence, Word]]:
        """Iterate over every word with its sentence."""
        for s in self.sentences:
            for w in s.words:
                yield s, w

    def concepts(self) -> Iterator[tuple[Sentence, Concept]]:
        """Iterate over every concept with its sentence."""
        for s in self.sentences:
            for c in s.concepts:
                yield s, c


@dataclass
class SentLink:
    """A sentence alignment between the from and to languages."""

    fsid: int
    tsid: int
    _: KW_ONLY
    ltype: str | None = None
    conf: float | None = None
    comment: str | None = None
    user: str | None = None


@dataclass
class WordLink:
    """A word alignment."""

    fsid: int
    fwid: int
    tsid: int
    twid: int
    _: KW_ONLY
    ltype: str | None = None
    conf: float | None = None
    comment: str | None = None
    user: str | None = None


@dataclass
class ConceptLink:
    """A concept alignment; ltype is the wordnet relation (=, <, >, ~, !)."""

    fsid: int
    fcid: int
    tsid: int
    tcid: int
    _: KW_ONLY
    ltype: str | None = None
    conf: float | None = None
    comment: str | None = None
    user: str | None = None


@dataclass
class Alignment:
    """The links from one language to another.

    When read from a database or a JSON file the links are grouped by
    the from-side document (``fdoc``); an in-memory corpus may hold
    several Alignment objects for the same language pair.
    """

    flang: str
    tlang: str
    _: KW_ONLY
    fdoc: int | None = None
    sents: list[SentLink] = field(default_factory=list)
    words: list[WordLink] = field(default_factory=list)
    concepts: list[ConceptLink] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.sents) + len(self.words) + len(self.concepts)


@dataclass
class CorpusInfo:
    """Corpus-level metadata (the ``meta`` table, the XML ``<Corpus>``)."""

    _: KW_ONLY
    title: str | None = None
    license: str | None = None
    version: str | None = None


Item = Document | Alignment | CorpusInfo


@dataclass
class Corpus:
    """An in-memory corpus: documents in any number of languages and links.

    Build one from a stream of items (``Corpus.from_items``) or add to it
    with ``add``.  Lookups go through ``document`` and ``sentence``;
    ``links_from`` and ``links_to`` find the alignments of a sentence.
    """

    _: KW_ONLY
    info: CorpusInfo = field(default_factory=CorpusInfo)
    documents: list[Document] = field(default_factory=list)
    alignments: list[Alignment] = field(default_factory=list)

    @classmethod
    def from_items(cls, items: Iterable[Item]) -> Corpus:
        """Collect a stream of documents, alignments and info into a corpus.

        Args:
            items: as yielded by the db or jsonl readers

        Returns:
            The corpus
        """
        corpus = cls()
        for item in items:
            corpus.add(item)
        return corpus

    def add(self, item: Item) -> None:
        """Add a document, alignment or corpus info.

        Args:
            item: the object to add; CorpusInfo replaces the current info
        """
        if isinstance(item, Document):
            self.documents.append(item)
        elif isinstance(item, Alignment):
            self.alignments.append(item)
        else:
            self.info = item

    def __iter__(self) -> Iterator[Item]:
        yield self.info
        yield from self.documents
        yield from self.alignments

    @property
    def languages(self) -> list[str]:
        """The languages with documents, in first-seen order."""
        seen: dict[str, None] = {}
        for d in self.documents:
            seen.setdefault(d.language, None)
        return list(seen)

    def document(self, language: str, doc: str | int) -> Document:
        """Return a document by name or docid.

        Args:
            language: language code
            doc: the short name (``'catb'``) or docid

        Returns:
            The document

        Raises:
            KeyError: if there is no such document
        """
        for d in self.documents:
            if d.language == language and doc in (d.doc, d.docid):
                return d
        raise KeyError(f"no document {doc!r} in {language}")

    def sentence(self, language: str, sid: int) -> Sentence:
        """Return a sentence by language and sid.

        Args:
            language: language code
            sid: sentence id

        Returns:
            The sentence

        Raises:
            KeyError: if there is no such sentence
        """
        for d in self.documents:
            if d.language != language:
                continue
            for s in d.sentences:
                if s.sid == sid:
                    return s
        raise KeyError(f"no sentence {sid} in {language}")

    def links_from(self, language: str, sid: int) -> list[tuple[str, SentLink]]:
        """Sentence links leaving a sentence, as (to language, link).

        Args:
            language: language of the sentence
            sid: its sid

        Returns:
            The links, in alignment order
        """
        return [
            (a.tlang, link)
            for a in self.alignments
            if a.flang == language
            for link in a.sents
            if link.fsid == sid
        ]

    def links_to(self, language: str, sid: int) -> list[tuple[str, SentLink]]:
        """Sentence links arriving at a sentence, as (from language, link).

        Args:
            language: language of the sentence
            sid: its sid

        Returns:
            The links, in alignment order
        """
        return [
            (a.flang, link)
            for a in self.alignments
            if a.tlang == language
            for link in a.sents
            if link.tsid == sid
        ]
