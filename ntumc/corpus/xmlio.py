"""The XML realisation of the corpus (``data/ntumc.dtd``).

``write`` streams model items to one XML file; ``read`` parses such a
file back into model items.  Element ids are ``LANG-dN``, ``LANG-sN``,
``LANG-sNwN``, ``LANG-sNcN`` and ``LANG-sNxN``; ``read`` keeps the
numbers when the ids have that shape (the language prefix is optional)
and otherwise numbers documents and sentences from 1 and words,
concepts and chunks by position.  The format is described in
``docs/corpus-xml.md``.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

from .index import Index
from .model import (
    Alignment,
    Chunk,
    Concept,
    ConceptLink,
    CorpusError,
    CorpusInfo,
    Document,
    Item,
    Sentence,
    SentLink,
    Word,
    WordLink,
)

DTD = Path(__file__).resolve().parents[2] / "data" / "ntumc.dtd"

# Characters that are not allowed in XML 1.0 text or attributes.
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_TAIL_NUM = re.compile(r"(\d+)$")


def clean(text: str | None) -> str | None:
    """Remove the characters XML 1.0 cannot carry.

    Args:
        text: Any string, or None

    Returns:
        The string without control characters, or None if text was None
    """
    if text is None:
        return None
    return _BAD_XML.sub("", str(text))


# ---------------------------------------------------------------------------
# model -> XML
# ---------------------------------------------------------------------------


def _set(el: ET.Element, name: str, value: object) -> None:
    if value is not None and value != "":
        el.set(name, clean(str(value)) or "")


def _tag(parent: ET.Element, category: str, value: object, **attrs: object) -> None:
    el = ET.SubElement(parent, "Tag", category=category, value=clean(str(value)) or "")
    for name, attr in attrs.items():
        _set(el, name, attr)


def _sid(lang: str, sid: int) -> str:
    return f"{lang}-s{sid}"


def document_element(doc: Document) -> ET.Element:
    """Build the ``<Document>`` element for one document.

    Args:
        doc: The document

    Returns:
        The element with all sentences, words, concepts, chunks and tags
    """
    lang = doc.language
    el = ET.Element("Document", docID=f"{lang}-d{doc.docid}")
    el.set("doc", clean(doc.doc) or "")
    el.set("language", lang)
    el.set("title", clean(doc.title) or "")
    _set(el, "subtitle", doc.subtitle)
    _set(el, "url", doc.url)
    _set(el, "collection", doc.collection)
    _set(el, "collection_title", doc.collection_title)
    _set(el, "genre", doc.genre)
    for s in doc.sentences:
        el.append(sentence_element(lang, s))
    return el


def sentence_element(lang: str, s: Sentence) -> ET.Element:
    """Build the ``<Sentence>`` element for one sentence.

    Args:
        lang: Language code used as the id prefix
        s: The sentence

    Returns:
        The element
    """
    sid = _sid(lang, s.sid)
    sel = ET.Element("Sentence", sid=sid)
    sel.set("sent", clean(s.text) or "")
    _set(sel, "pid", s.pid)
    _set(sel, "comment", s.comment)
    _set(sel, "last_changed_by", s.user)
    for w in s.words:
        wel = ET.SubElement(sel, "Word", wid=f"{sid}w{w.wid}")
        _set(wel, "lemma", w.lemma)
        wel.set("surface_form", clean(w.word) or "")
        _set(wel, "pos", w.pos)
        _set(wel, "cfrom", w.cfrom)
        _set(wel, "cto", w.cto)
        _set(wel, "comment", w.comment)
        _set(wel, "last_changed_by", w.user)
    for c in s.concepts:
        cel = ET.SubElement(sel, "Concept", cid=f"{sid}c{c.cid}")
        _set(cel, "wid", " ".join(f"{sid}w{w}" for w in c.wids))
        cel.set("clemma", clean(c.clemma) or "")
        _set(cel, "synset_tag", c.tag)
        _set(cel, "comment", c.comment)
        _set(cel, "last_changed_by", c.user)
        if c.ne:
            _tag(cel, "ne", c.ne)
        if c.candidates:
            _tag(cel, "candidates", "; ".join(c.candidates))
        if c.sentiment is not None:
            _tag(cel, "sentiment", c.sentiment, last_changed_by=c.sentiment_user)
    for x in s.chunks:
        xel = ET.SubElement(sel, "Chunk", chid=f"{sid}x{x.xid}")
        _set(xel, "wid", " ".join(f"{sid}w{w}" for w in x.wids))
        _set(xel, "comment", x.comment)
        _set(xel, "last_changed_by", x.user)
        if x.score is not None:
            _tag(xel, "sentiment", x.score)
    if s.stype:
        _tag(sel, "stype", s.stype, comment=s.stype_comment)
    return sel


def alignment_element(alignments: Iterable[Alignment]) -> ET.Element:
    """Build one ``<Alignment>`` element from any number of alignments.

    Args:
        alignments: The alignments (any language pairs)

    Returns:
        The element, grouped as the DTD orders: sentence, word, concept links
    """
    al = ET.Element("Alignment")
    groups: dict[str, list[ET.Element]] = {
        "SentAlignment": [],
        "WordAlignment": [],
        "ConceptAlignment": [],
    }
    for a in alignments:
        for link in a.sents:
            fid, tid = _sid(a.flang, link.fsid), _sid(a.tlang, link.tsid)
            groups["SentAlignment"].append(
                _link_element("SentAlignment", "sid", fid, tid, link)
            )
        for link in a.words:
            fid = f"{_sid(a.flang, link.fsid)}w{link.fwid}"
            tid = f"{_sid(a.tlang, link.tsid)}w{link.twid}"
            groups["WordAlignment"].append(
                _link_element("WordAlignment", "wid", fid, tid, link)
            )
        for link in a.concepts:
            fid = f"{_sid(a.flang, link.fsid)}c{link.fcid}"
            tid = f"{_sid(a.tlang, link.tsid)}c{link.tcid}"
            groups["ConceptAlignment"].append(
                _link_element("ConceptAlignment", "cid", fid, tid, link)
            )
    for els in groups.values():
        al.extend(els)
    return al


def _link_element(
    tag: str, attr: str, fid: str, tid: str, link: SentLink | WordLink | ConceptLink
) -> ET.Element:
    el = ET.Element(tag, {f"{attr}_from": fid, f"{attr}_to": tid})
    if link.ltype == "automatic":
        el.set("type", "automatic")
    elif link.ltype and link.ltype != "manual":
        _set(el, "ltype", link.ltype)
    _set(el, "conf", link.conf)
    _set(el, "comment", link.comment)
    _set(el, "last_changed_by", link.user)
    return el


@dataclass
class XMLOptions:
    """Attributes of the ``<Corpus>`` element; None falls back to the CorpusInfo."""

    corpus_id: str = "ntumc"
    title: str | None = None
    license: str | None = None
    version: str | None = None
    linguality: str = "multilingual"
    dtd: Path = DTD


def write(
    items: Iterable[Item], out: Path | str, opts: XMLOptions | None = None
) -> dict[str, int]:
    """Write items as one XML file, streaming one document at a time.

    A copy of the DTD is put beside the output so that the DOCTYPE
    resolves.  A CorpusInfo item supplies the title, license and version
    unless opts gives them; it must come before the first document.

    Args:
        items: CorpusInfo, documents and alignments, documents first
        out: Path of the XML file
        opts: Corpus attributes

    Returns:
        Documents per language and the number of alignment elements
    """
    opts = opts or XMLOptions()
    out = Path(out)
    counts: dict[str, int] = {}
    alignments: list[Alignment] = []
    with open(out, "w", encoding="utf-8") as fh:
        started = False
        for item in items:
            if isinstance(item, CorpusInfo):
                if started:
                    raise CorpusError("CorpusInfo must come before the documents")
                _start(fh, item, opts)
                started = True
                continue
            if not started:
                _start(fh, CorpusInfo(), opts)
                started = True
            if isinstance(item, Document):
                el = document_element(item)
                ET.indent(el, level=1)
                fh.write("  " + ET.tostring(el, encoding="unicode") + "\n")
                counts[item.language] = counts.get(item.language, 0) + 1
            else:
                alignments.append(item)
        if not started:
            _start(fh, CorpusInfo(), opts)
        al = alignment_element(alignments)
        if len(al):
            ET.indent(al, level=1)
            fh.write("  " + ET.tostring(al, encoding="unicode") + "\n")
            counts["alignments"] = len(al)
        fh.write("</Corpus>\n")
    shutil.copy(opts.dtd, out.parent / opts.dtd.name)
    return counts


def _start(fh: IO[str], info: CorpusInfo, opts: XMLOptions) -> None:
    attrs = {
        "corpusID": opts.corpus_id,
        "title": opts.title or info.title or "NTU Multilingual Corpus",
        "linguality": opts.linguality,
        "license": opts.license or info.license,
        "version": opts.version or info.version,
    }
    fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    fh.write('<!DOCTYPE Corpus SYSTEM "ntumc.dtd">\n<Corpus')
    for name, value in attrs.items():
        if value:
            fh.write(f"\n        {name}={quoteattr(clean(value) or '')}")
    fh.write(">\n")


# ---------------------------------------------------------------------------
# XML -> model
# ---------------------------------------------------------------------------

_SUB_LETTERS = {"w": "word", "c": "concept", "x": "chunk"}


@dataclass
class _Reader:
    """Parsing state: the ids assigned so far."""

    corpus_attrs: dict[str, str] = field(default_factory=dict)
    next_docid: dict[str, int] = field(default_factory=dict)
    next_sid: dict[str, int] = field(default_factory=dict)
    doc_ids: set[str] = field(default_factory=set)
    # sentence xml id -> (lang, sid, docid)
    sents: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    # word/concept/chunk xml ids that are not <sentence id><letter><n>
    subs: dict[str, tuple[str, int, int]] = field(default_factory=dict)
    index: Index = field(default_factory=Index)

    def info(self, el: ET.Element) -> CorpusInfo:
        self.corpus_attrs = dict(el.attrib)
        return CorpusInfo(
            title=el.get("title"), license=el.get("license"), version=el.get("version")
        )

    def _number(self, counters: dict[str, int], lang: str, xmlid: str) -> int:
        m = _TAIL_NUM.search(xmlid)
        n = int(m.group(1)) if m else counters.get(lang, 1)
        counters[lang] = max(counters.get(lang, 1), n + 1)
        return n

    def document(self, el: ET.Element) -> Document:
        lang = el.get("language")
        xmlid = el.get("docID", "")
        if not lang:
            raise CorpusError(f"document {xmlid} has no language")
        if xmlid in self.doc_ids:
            raise CorpusError(f"duplicate document id {xmlid}")
        self.doc_ids.add(xmlid)
        docid = self._number(self.next_docid, lang, xmlid)
        doc = Document(
            docid,
            el.get("doc") or f"doc{docid}",
            lang,
            title=el.get("title") or "",
            subtitle=el.get("subtitle"),
            url=el.get("url"),
            collection=el.get("collection") or self.corpus_attrs.get("corpusID"),
            collection_title=el.get("collection_title"),
            genre=el.get("genre"),
        )
        doc.sentences = [
            self.sentence(lang, docid, sel) for sel in el.findall("Sentence")
        ]
        for message in self.index.add(doc):
            raise CorpusError(message)
        return doc

    def sentence(self, lang: str, docid: int, sel: ET.Element) -> Sentence:
        xmlid = sel.get("sid", "")
        if xmlid in self.sents:
            raise CorpusError(f"duplicate sentence id {xmlid}")
        sid = self._number(self.next_sid, lang, xmlid)
        self.sents[xmlid] = (lang, sid, docid)
        s = Sentence(
            sid,
            sel.get("sent") or "",
            pid=sel.get("pid"),
            comment=sel.get("comment"),
            user=sel.get("last_changed_by"),
        )
        for tag in sel.findall("Tag"):
            if tag.get("category") == "stype":
                s.stype, s.stype_comment = tag.get("value"), tag.get("comment")
        for i, wel in enumerate(sel.findall("Word")):
            s.words.append(
                Word(
                    self._sub_id(lang, sid, xmlid, wel.get("wid", ""), "w", i),
                    wel.get("surface_form") or "",
                    lemma=wel.get("lemma"),
                    pos=wel.get("pos") or wel.get("upos"),
                    cfrom=_int(wel.get("cfrom")),
                    cto=_int(wel.get("cto")),
                    comment=wel.get("comment"),
                    user=wel.get("last_changed_by"),
                )
            )
        wids = {w.wid for w in s.words}
        for i, cel in enumerate(sel.findall("Concept")):
            tags = {t.get("category"): t for t in cel.findall("Tag")}
            senti = tags.get("sentiment")
            cands = _value(tags.get("candidates")) or ""
            s.concepts.append(
                Concept(
                    self._sub_id(lang, sid, xmlid, cel.get("cid", ""), "c", i),
                    cel.get("clemma") or "",
                    tag=cel.get("synset_tag"),
                    wids=self._word_refs(cel.get("wid", ""), xmlid, lang, sid, wids),
                    ne=_value(tags.get("ne")),
                    candidates=[c.strip() for c in cands.split(";") if c.strip()],
                    sentiment=_float(_value(senti)),
                    sentiment_user=senti.get("last_changed_by")
                    if senti is not None
                    else None,
                    comment=cel.get("comment"),
                    user=cel.get("last_changed_by"),
                )
            )
        for i, xel in enumerate(sel.findall("Chunk")):
            tags = {t.get("category"): t for t in xel.findall("Tag")}
            s.chunks.append(
                Chunk(
                    self._sub_id(lang, sid, xmlid, xel.get("chid", ""), "x", i),
                    wids=self._word_refs(xel.get("wid", ""), xmlid, lang, sid, wids),
                    score=_float(_value(tags.get("sentiment"))),
                    comment=xel.get("comment"),
                    user=xel.get("last_changed_by"),
                )
            )
        return s

    def _sub_id(
        self, lang: str, sid: int, sent_xmlid: str, xmlid: str, letter: str, i: int
    ) -> int:
        m = re.fullmatch(re.escape(sent_xmlid) + letter + r"(\d+)", xmlid)
        if m:
            return int(m.group(1))
        if xmlid in self.subs:
            raise CorpusError(f"duplicate id {xmlid}")
        self.subs[xmlid] = (lang, sid, i)
        return i

    def _word_refs(
        self, refs: str, sent_xmlid: str, lang: str, sid: int, wids: set[int]
    ) -> list[int]:
        out = []
        for ref in refs.split():
            rlang, rsid, wid = self._resolve(
                ref, "w", current=(sent_xmlid, lang, sid, wids)
            )
            if (rlang, rsid) != (lang, sid):
                raise CorpusError(f"{ref} is not a word of sentence {sent_xmlid}")
            out.append(wid)
        return sorted(out)

    def _resolve(
        self,
        ref: str,
        letter: str,
        current: tuple[str, str, int, set[int]] | None = None,
    ) -> tuple[str, int, int]:
        """Resolve a word/concept/chunk reference to (lang, sid, n)."""
        if ref in self.subs:
            lang, sid, n = self.subs[ref]
            if self._has(lang, sid, n, letter, current):
                return lang, sid, n
        m = re.fullmatch(r"(.+)" + letter + r"(\d+)", ref)
        if m and m.group(1) in self.sents:
            lang, sid, _ = self.sents[m.group(1)]
            n = int(m.group(2))
            if self._has(lang, sid, n, letter, current):
                return lang, sid, n
        raise CorpusError(f"reference to unknown id {ref}")

    def _has(
        self,
        lang: str,
        sid: int,
        n: int,
        letter: str,
        current: tuple[str, str, int, set[int]] | None,
    ) -> bool:
        if current is not None and (lang, sid) == (current[1], current[2]):
            return n in current[3]
        if letter == "w":
            return self.index.has_word(lang, sid, n)
        if letter == "c":
            return self.index.has_concept(lang, sid, n)
        return n in self.index.xids.get((lang, sid), ())

    def resolve_sent(self, ref: str) -> tuple[str, int, int]:
        """Resolve a sentence reference to (lang, sid, docid)."""
        if ref not in self.sents:
            raise CorpusError(f"reference to unknown sentence id {ref}")
        return self.sents[ref]

    def alignments(self, al: ET.Element) -> Iterator[Alignment]:
        """Turn an ``<Alignment>`` element into alignments per pair and from-document."""
        groups: dict[tuple[str, str, int], Alignment] = {}

        def group(flang: str, tlang: str, fdoc: int) -> Alignment:
            return groups.setdefault(
                (flang, tlang, fdoc), Alignment(flang, tlang, fdoc=fdoc)
            )

        for el in al.findall("SentAlignment"):
            flang, fsid, fdoc = self.resolve_sent(el.get("sid_from", ""))
            for ref in el.get("sid_to", "").split():
                tlang, tsid, _ = self.resolve_sent(ref)
                group(flang, tlang, fdoc).sents.append(
                    SentLink(fsid, tsid, **_link_attrs(el))
                )
        for el in al.findall("WordAlignment"):
            flang, fsid, fwid = self._resolve(el.get("wid_from", ""), "w")
            fdoc = self._doc_of(flang, fsid)
            for ref in el.get("wid_to", "").split():
                tlang, tsid, twid = self._resolve(ref, "w")
                group(flang, tlang, fdoc).words.append(
                    WordLink(fsid, fwid, tsid, twid, **_link_attrs(el))
                )
        for el in al.findall("ConceptAlignment"):
            flang, fsid, fcid = self._resolve(el.get("cid_from", ""), "c")
            fdoc = self._doc_of(flang, fsid)
            for ref in el.get("cid_to", "").split():
                tlang, tsid, tcid = self._resolve(ref, "c")
                group(flang, tlang, fdoc).concepts.append(
                    ConceptLink(fsid, fcid, tsid, tcid, **_link_attrs(el))
                )
        yield from groups.values()

    def _doc_of(self, lang: str, sid: int) -> int:
        for rlang, rsid, docid in self.sents.values():
            if (rlang, rsid) == (lang, sid):
                return docid
        raise CorpusError(f"no document for sentence {lang} s{sid}")


def _link_attrs(el: ET.Element) -> dict[str, object]:
    ltype = el.get("ltype")
    if ltype is None and el.get("type") == "automatic":
        ltype = "automatic"
    return {
        "ltype": ltype,
        "conf": _float(el.get("conf")),
        "comment": el.get("comment"),
        "user": el.get("last_changed_by"),
    }


def _value(tag: ET.Element | None) -> str | None:
    return None if tag is None else tag.get("value")


def _int(text: str | None) -> int | None:
    if text in (None, ""):
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _float(text: str | None) -> float | None:
    return None if text in (None, "") else float(text)


def read(path: Path | str) -> Iterator[Item]:
    """Yield the items of an XML file: CorpusInfo, documents, alignments.

    Args:
        path: The XML file

    Yields:
        One item at a time, documents before the alignments

    Raises:
        CorpusError: On duplicate or dangling ids or a document without a language
    """
    reader = _Reader()
    for event, el in ET.iterparse(path, events=("start", "end")):
        if event == "start" and el.tag == "Corpus":
            yield reader.info(el)
        elif event == "end" and el.tag == "Document":
            yield reader.document(el)
            el.clear()
        elif event == "end" and el.tag == "Alignment":
            yield from reader.alignments(el)
            el.clear()
