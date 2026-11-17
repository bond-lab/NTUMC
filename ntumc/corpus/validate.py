"""Semantic checks on a corpus, whatever it was read from.

The format-level checks (DTD, JSON shape, SQL schema) belong to each
realisation; this module checks what they cannot: that ids are unique,
that concepts and chunks cover words that exist, that offsets match the
text, that tags are well formed, and that every link joins two things
that are present.  It works on the streamed items so that a whole
corpus can be checked without holding it in memory.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .index import Index
from .model import GENRES, META_TAGS, Alignment, Document, Item, Sentence

# NTU-MC adds synsets of its own with other letters (76000000-x, 80002126-z)
SYNSET = re.compile(r"^\d{8}-[a-z]$")
UNKNOWN_CANDIDATE = "unk"
NE_TAGS = ("per", "org", "loc", "dat", "num", "oth", "nam")


@dataclass
class Problem:
    """One finding; ``level`` is 'error' or 'warning'."""

    level: str
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level} {self.code} {self.where}: {self.message}"


def check_document(doc: Document) -> Iterator[Problem]:
    """Check one document on its own.

    Args:
        doc: the document

    Yields:
        Problems found
    """
    where = f"{doc.language} d{doc.docid}"
    if not doc.doc:
        yield Problem("error", "no-name", where, "document has no name")
    if doc.genre is not None and doc.genre not in GENRES:
        yield Problem("error", "genre", where, f"unknown genre {doc.genre!r}")
    if not doc.sentences:
        yield Problem("warning", "empty-doc", where, "no sentences")
    for s in doc.sentences:
        yield from check_sentence(doc.language, s)


def check_sentence(lang: str, s: Sentence) -> Iterator[Problem]:
    """Check the words, concepts and chunks of one sentence.

    Args:
        lang: language of the sentence
        s: the sentence

    Yields:
        Problems found
    """
    where = f"{lang} s{s.sid}"
    wids = [w.wid for w in s.words]
    if len(set(wids)) != len(wids):
        yield Problem("error", "dup-wid", where, "duplicate wid")
    if wids and wids != sorted(wids):
        yield Problem("warning", "wid-order", where, "words not in wid order")
    for w in s.words:
        if (w.cfrom is None) != (w.cto is None):
            yield Problem(
                "error", "offset", f"{where}w{w.wid}", "only one of cfrom/cto set"
            )
        elif w.cfrom is not None and w.cto is not None:
            if not (0 <= w.cfrom <= w.cto <= len(s.text)):
                yield Problem(
                    "error", "offset", f"{where}w{w.wid}", "offsets outside the text"
                )
            elif s.text[w.cfrom : w.cto] != w.word:
                yield Problem(
                    "warning",
                    "offset",
                    f"{where}w{w.wid}",
                    f"text at offsets is {s.text[w.cfrom : w.cto]!r}, word is {w.word!r}",
                )
    widset = set(wids)
    cids = [c.cid for c in s.concepts]
    if len(set(cids)) != len(cids):
        yield Problem("error", "dup-cid", where, "duplicate cid")
    if cids and min(cids) != 0:
        yield Problem("warning", "cid-base", where, f"cids start at {min(cids)}, not 0")
    for c in s.concepts:
        cwhere = f"{where}c{c.cid}"
        if not c.wids:
            yield Problem("warning", "no-words", cwhere, "concept covers no words")
        for wid in c.wids:
            if wid not in widset:
                yield Problem("error", "bad-wid", cwhere, f"covers missing word {wid}")
        if c.tag and c.tag not in META_TAGS and not SYNSET.match(c.tag):
            yield Problem(
                "warning", "tag", cwhere, f"tag {c.tag!r} is not a synset or e/w/x"
            )
        if c.ne is not None and c.ne not in NE_TAGS:
            yield Problem(
                "warning", "ne", cwhere, f"unknown named-entity type {c.ne!r}"
            )
        for cand in c.candidates:
            if cand != UNKNOWN_CANDIDATE and not SYNSET.match(cand):
                yield Problem(
                    "warning",
                    "candidate",
                    cwhere,
                    f"candidate {cand!r} is not a synset",
                )
    xids = [x.xid for x in s.chunks]
    if len(set(xids)) != len(xids):
        yield Problem("error", "dup-xid", where, "duplicate chunk id")
    for x in s.chunks:
        for wid in x.wids:
            if wid not in widset:
                yield Problem(
                    "error", "bad-wid", f"{where}x{x.xid}", f"covers missing word {wid}"
                )


def check_alignment(a: Alignment, index: Index) -> Iterator[Problem]:
    """Check that every link joins two things in the index.

    Args:
        a: the alignment
        index: the documents seen so far

    Yields:
        Problems found
    """
    where = f"{a.flang}-{a.tlang}"
    for link in a.sents:
        for lang, sid in ((a.flang, link.fsid), (a.tlang, link.tsid)):
            if (lang, sid) not in index.wids:
                yield Problem(
                    "error", "link-sent", where, f"sentence {lang} s{sid} missing"
                )
    for link in a.words:
        for lang, sid, wid in (
            (a.flang, link.fsid, link.fwid),
            (a.tlang, link.tsid, link.twid),
        ):
            if wid not in index.wids.get((lang, sid), ()):
                yield Problem(
                    "error", "link-word", where, f"word {lang} s{sid}w{wid} missing"
                )
    for link in a.concepts:
        for lang, sid, cid in (
            (a.flang, link.fsid, link.fcid),
            (a.tlang, link.tsid, link.tcid),
        ):
            if cid not in index.cids.get((lang, sid), ()):
                yield Problem(
                    "error",
                    "link-concept",
                    where,
                    f"concept {lang} s{sid}c{cid} missing",
                )


def validate(items: Iterable[Item]) -> Iterator[Problem]:
    """Check a stream of documents and alignments.

    Documents must come before the alignments that refer to them, as
    the readers yield them.

    Args:
        items: from a db or jsonl reader, or a Corpus

    Yields:
        Problems in the order found
    """
    index = Index()
    for item in items:
        if isinstance(item, Document):
            yield from check_document(item)
            for message in index.add(item):
                where, _, text = message.partition(": ")
                yield Problem("error", "dup-id", where, text)
        elif isinstance(item, Alignment):
            yield from check_alignment(item, index)
