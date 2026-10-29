#!/usr/bin/env python3
"""Convert NTU-MC corpus databases to XML and back.

The XML format is defined by ``data/ntumc.dtd`` and described in
``docs/corpus-xml.md``.  One file holds any number of languages: each
``<Document>`` carries its own language, and an ``<Alignment>`` block at
the end holds the cross-lingual sentence, word and concept links that
the per-pair link databases store.

Usage::

    corpus_xml.py dump OUT.xml --db eng.db jpn.db [--link eng-jpn.db ...]
                  [--doc NAME ...] [--collection NAME ...]
    corpus_xml.py load IN.xml --outdir DIR [--renumber] [--user NAME]
    corpus_xml.py validate FILE.xml [--dtd data/ntumc.dtd]

``dump`` writes one XML file from one or more language databases plus
their link databases.  ``load`` creates (or appends to) ``LANG.db`` and
``FLANG-TLANG.db`` files in DIR from such a file.  Element ids follow
``LANG-dN``, ``LANG-sN``, ``LANG-sNwN``, ``LANG-sNcN`` and ``LANG-sNxN``;
``load`` keeps the numbers when the ids have that shape and the numbers
are free, and assigns fresh numbers otherwise (always with ``--renumber``).
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import quoteattr

logger = logging.getLogger("corpus_xml")

REPO = Path(__file__).resolve().parent.parent
DTD = REPO / "data" / "ntumc.dtd"
SCHEMA = REPO / "data" / "ntumc.sql"
LINK_SCHEMA = REPO / "data" / "link.sql"
GENRES = ("essay", "fiction", "lexical", "news", "online", "tourism")

# Characters that are not allowed in XML 1.0 text or attributes.
_BAD_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_TAIL_NUM = re.compile(r"(\d+)$")


def clean(text: str | None) -> str | None:
    """Strip characters that XML 1.0 forbids from a string.

    Args:
        text: Any database string, or None

    Returns:
        The string without control characters, or None if text was None
    """
    if text is None:
        return None
    return _BAD_XML.sub("", str(text))


def db_lang(path: Path) -> str:
    """Return the language of a corpus database.

    Args:
        path: Path to a per-language database

    Returns:
        ``meta.lang`` if present, else the file stem (e.g. 'eng')
    """
    con = sqlite3.connect(path)
    try:
        row = con.execute("SELECT lang FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    return row[0] if row and row[0] else path.stem


def link_langs(path: Path) -> tuple[str, str]:
    """Return the (from, to) languages of a link database.

    Args:
        path: Path to a link database such as ``eng-jpn.db``

    Returns:
        ``(flang, tlang)`` from ``meta`` if present, else from the file stem

    Raises:
        ValueError: If neither source gives two languages
    """
    con = sqlite3.connect(path)
    try:
        row = con.execute("SELECT flang, tlang FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    if row and row[0] and row[1]:
        return row[0], row[1]
    parts = path.stem.split("-")
    if len(parts) != 2:
        raise ValueError(f"cannot tell the languages of {path}; add a meta row")
    return parts[0], parts[1]


def has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if ``table`` has ``column``."""
    return any(r[1] == column for r in con.execute(f"PRAGMA table_info({table})"))


# ---------------------------------------------------------------------------
# dump: database -> XML
# ---------------------------------------------------------------------------


def _text(value: object) -> str:
    """Render a database value as attribute text (integral floats as ints)."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return clean(str(value))


def _set(el: ET.Element, name: str, value: object) -> None:
    """Set an attribute unless the value is None or an empty string."""
    if value is None or value == "":
        return
    el.set(name, _text(value))


def _tag(parent: ET.Element, category: str, value: object, **attrs: object) -> None:
    """Append a ``<Tag>`` child with the given category and value."""
    tag = ET.SubElement(parent, "Tag", category=category, value=_text(value))
    for name, val in attrs.items():
        _set(tag, name, val)


def _by_sid(rows: list[sqlite3.Row]) -> dict[int, list[sqlite3.Row]]:
    """Group rows by their ``sid`` column."""
    out: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        out[row["sid"]].append(row)
    return out


# Columns read from each annotation table when dumping a document.
DOC_TABLES = {
    "word": "sid, wid, word, pos, lemma, cfrom, cto, comment, usrname",
    "concept": "sid, cid, clemma, tag, tags, comment, ntag, usrname",
    "cwl": "sid, wid, cid",
    "sentiment": "sid, cid, score, username",
    "stype": "sid, stype, comment",
    "chunks": "sid, xid, score, comment, username",
    "xwl": "sid, wid, xid",
}
LINK_TABLES = {
    "slink": "fsid, tsid, ltype, conf, comment, usrname",
    "wlink": "fsid, fwid, tsid, twid, ltype, conf, comment, usrname",
    "clink": "fsid, fcid, tsid, tcid, ltype, conf, comment, usrname",
}


def _select_list(con: sqlite3.Connection, table: str, wanted: str) -> str | None:
    """Build a select list for ``table``, substituting NULL for absent columns.

    The language databases differ slightly (older ones lack ``concept.ntag``,
    some have no ``chunks`` table), so the dump adapts to what is there.

    Returns:
        The select list, or None if the table does not exist or is empty
    """
    present = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if not present:
        return None
    cols = [c.strip() for c in wanted.split(",")]
    return ", ".join(c if c in present else f"NULL AS {c}" for c in cols)


def _doc_rows(con: sqlite3.Connection, table: str, docid: int) -> list[sqlite3.Row]:
    """Fetch every row of ``table`` for the sentences of a document."""
    select = _select_list(con, table, DOC_TABLES[table])
    if select is None:
        return []
    return con.execute(
        f"SELECT {select} FROM {table} WHERE sid IN (SELECT sid FROM sent WHERE docID = ?)",
        (docid,),
    ).fetchall()


def document_element(
    con: sqlite3.Connection, lang: str, doc: sqlite3.Row
) -> ET.Element:
    """Build the ``<Document>`` element for one document.

    Args:
        con: Connection to the language database (row_factory = sqlite3.Row)
        lang: Language code used as the id prefix
        doc: Row with docid, doc, title, url, subtitle, corpus, corpus_title, genre

    Returns:
        The element, with all sentences, words, concepts, chunks and tags
    """
    docid = doc["docid"]
    el = ET.Element("Document", docID=f"{lang}-d{docid}")
    _set(el, "doc", doc["doc"])
    el.set("language", lang)
    el.set("title", clean(doc["title"]) or "")
    _set(el, "subtitle", doc["subtitle"])
    _set(el, "url", doc["url"])
    _set(el, "collection", doc["corpus"])
    _set(el, "collection_title", doc["corpus_title"])
    _set(el, "genre", doc["genre"])

    sents = con.execute(
        "SELECT sid, pid, sent, comment, usrname FROM sent WHERE docID = ? ORDER BY sid",
        (docid,),
    ).fetchall()
    words = _by_sid(_doc_rows(con, "word", docid))
    concepts = _by_sid(_doc_rows(con, "concept", docid))
    cwl = _by_sid(_doc_rows(con, "cwl", docid))
    senti = {(r["sid"], r["cid"]): r for r in _doc_rows(con, "sentiment", docid)}
    stypes = _by_sid(_doc_rows(con, "stype", docid))
    chunks = _by_sid(_doc_rows(con, "chunks", docid))
    xwl = _by_sid(_doc_rows(con, "xwl", docid))

    for sent in sents:
        sid = sent["sid"]
        sel = ET.SubElement(el, "Sentence", sid=f"{lang}-s{sid}")
        sel.set("sent", clean(sent["sent"]) or "")
        _set(sel, "pid", sent["pid"])
        _set(sel, "comment", sent["comment"])
        _set(sel, "last_changed_by", sent["usrname"])

        for w in sorted(words.get(sid, []), key=lambda r: r["wid"]):
            wel = ET.SubElement(sel, "Word", wid=f"{lang}-s{sid}w{w['wid']}")
            _set(wel, "lemma", w["lemma"])
            wel.set("surface_form", clean(w["word"]) or "")
            _set(wel, "pos", w["pos"])
            _set(wel, "cfrom", w["cfrom"])
            _set(wel, "cto", w["cto"])
            _set(wel, "comment", w["comment"])
            _set(wel, "last_changed_by", w["usrname"])

        cwl_wids: dict[int, list[int]] = defaultdict(list)
        for link in cwl.get(sid, []):
            cwl_wids[link["cid"]].append(link["wid"])
        for c in sorted(concepts.get(sid, []), key=lambda r: r["cid"]):
            cid = c["cid"]
            cel = ET.SubElement(sel, "Concept", cid=f"{lang}-s{sid}c{cid}")
            _set(
                cel,
                "wid",
                " ".join(f"{lang}-s{sid}w{w}" for w in sorted(cwl_wids.get(cid, []))),
            )
            cel.set("clemma", clean(c["clemma"]) or "")
            _set(cel, "synset_tag", c["tag"])
            _set(cel, "comment", c["comment"])
            _set(cel, "last_changed_by", c["usrname"])
            if c["ntag"]:
                _tag(cel, "ne", c["ntag"])
            if c["tags"]:
                _tag(cel, "candidates", c["tags"])
            s = senti.get((sid, cid))
            if s is not None and s["score"] is not None:
                _tag(cel, "sentiment", s["score"], last_changed_by=s["username"])

        xwl_wids: dict[int, list[int]] = defaultdict(list)
        for link in xwl.get(sid, []):
            xwl_wids[link["xid"]].append(link["wid"])
        for x in sorted(chunks.get(sid, []), key=lambda r: r["xid"]):
            xid = x["xid"]
            xel = ET.SubElement(sel, "Chunk", chid=f"{lang}-s{sid}x{xid}")
            _set(
                xel,
                "wid",
                " ".join(f"{lang}-s{sid}w{w}" for w in sorted(xwl_wids.get(xid, []))),
            )
            _set(xel, "comment", x["comment"])
            _set(xel, "last_changed_by", x["username"])
            if x["score"] is not None:
                _tag(xel, "sentiment", x["score"])

        for st in stypes.get(sid, []):
            _tag(sel, "stype", st["stype"], comment=st["comment"])
    return el


def iter_documents(
    db: Path, docs: set[str] | None = None, collections: set[str] | None = None
) -> Iterator[tuple[str, ET.Element, set[str]]]:
    """Yield ``(lang, element, sids)`` for each document of a database.

    Args:
        db: Path to a per-language database
        docs: If given, only documents with these ``doc`` names
        collections: If given, only documents in these sub-corpora

    Yields:
        The language, the ``<Document>`` element and the set of its sids
    """
    lang = db_lang(db)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    genre = "c.genre" if has_column(con, "corpus", "genre") else "NULL AS genre"
    rows = con.execute(
        "SELECT d.docid, d.doc, d.title, d.url, d.subtitle, "
        f"c.corpus, c.title AS corpus_title, {genre} "
        "FROM doc d LEFT JOIN corpus c ON d.corpusID = c.corpusID ORDER BY d.docid"
    ).fetchall()
    for doc in rows:
        if docs is not None and doc["doc"] not in docs:
            continue
        if collections is not None and doc["corpus"] not in collections:
            continue
        el = document_element(con, lang, doc)
        ids = {e.get(a) for a, e in _ids(el)}
        yield lang, el, ids
    con.close()


def _ids(el: ET.Element) -> Iterator[tuple[str, ET.Element]]:
    """Yield ``(id attribute, element)`` for the sentences, words and concepts."""
    for sel in el.iter("Sentence"):
        yield "sid", sel
        for wel in sel.iter("Word"):
            yield "wid", wel
        for cel in sel.iter("Concept"):
            yield "cid", cel


def alignment_element(links: list[Path], dumped: dict[str, set[str]]) -> ET.Element:
    """Build the ``<Alignment>`` element from link databases.

    Only links whose two ends were dumped are written; the rest (links to
    documents left out, or dangling links) are counted in a warning.

    Args:
        links: Paths to link databases (``slink``, ``wlink``, ``clink`` tables)
        dumped: Language code to the set of element ids written for it

    Returns:
        The element (possibly empty)
    """
    al = ET.Element("Alignment")
    groups: dict[str, list[ET.Element]] = {
        "SentAlignment": [],
        "WordAlignment": [],
        "ConceptAlignment": [],
    }
    specs = [
        ("slink", "SentAlignment", "sid", "", "fsid", "tsid", None, None),
        ("wlink", "WordAlignment", "wid", "w", "fsid", "tsid", "fwid", "twid"),
        ("clink", "ConceptAlignment", "cid", "c", "fsid", "tsid", "fcid", "tcid"),
    ]
    for path in links:
        flang, tlang = link_langs(path)
        if flang not in dumped or tlang not in dumped:
            logger.warning("skipping %s: %s or %s not dumped", path, flang, tlang)
            continue
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        for table, tag, attr, letter, fs, ts, fsub, tsub in specs:
            select = _select_list(con, table, LINK_TABLES[table])
            if select is None:
                continue
            rows = con.execute(f"SELECT {select} FROM {table}").fetchall()
            skipped = 0
            for r in rows:
                fid = f"{flang}-s{r[fs]}" + (f"{letter}{r[fsub]}" if fsub else "")
                tid = f"{tlang}-s{r[ts]}" + (f"{letter}{r[tsub]}" if tsub else "")
                if fid not in dumped[flang] or tid not in dumped[tlang]:
                    skipped += 1
                    continue
                el = ET.Element(tag, {f"{attr}_from": fid, f"{attr}_to": tid})
                groups[tag].append(el)
                ltype = r["ltype"]
                if ltype == "automatic":
                    el.set("type", "automatic")
                elif ltype and ltype != "manual":
                    _set(el, "ltype", ltype)
                _set(el, "conf", r["conf"])
                _set(el, "comment", r["comment"])
                _set(el, "last_changed_by", r["usrname"])
            if skipped:
                logger.warning(
                    "%s: %d of %d %s rows left out (ends not dumped)",
                    path.name,
                    skipped,
                    len(rows),
                    table,
                )
        con.close()
    # The DTD orders the link types, so group them.
    for els in groups.values():
        al.extend(els)
    return al


def db_meta(db: Path) -> dict[str, str | None]:
    """Return the ``meta`` row of a database as a dict (empty if none)."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT title, license, lang, version FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    return dict(row) if row else {}


@dataclass
class DumpOptions:
    """What to write and how to label the ``<Corpus>`` element."""

    dbs: list[Path]
    links: list[Path] = field(default_factory=list)
    docs: set[str] | None = None
    collections: set[str] | None = None
    corpus_id: str = "ntumc"
    title: str | None = None
    license: str | None = None
    version: str | None = None


def dump(out: Path, opts: DumpOptions) -> dict[str, int]:
    """Write one XML file from language and link databases.

    Documents are streamed one at a time, so the whole corpus fits.  A copy
    of the DTD is put beside the output so that the DOCTYPE resolves.

    Args:
        out: Path of the XML file to write
        opts: Databases, filters and corpus-level labels

    Returns:
        Counts: documents per language and alignment elements

    Raises:
        ValueError: If no database is given
    """
    if not opts.dbs:
        raise ValueError("at least one language database is needed")
    meta = db_meta(opts.dbs[0])
    attrs = {
        "corpusID": opts.corpus_id,
        "title": opts.title or meta.get("title") or "NTU Multilingual Corpus",
        "linguality": "multilingual" if len(opts.dbs) > 1 else "monolingual",
        "license": opts.license or meta.get("license"),
        "version": opts.version or meta.get("version"),
    }
    counts: dict[str, int] = defaultdict(int)
    dumped: dict[str, set[str]] = defaultdict(set)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write('<!DOCTYPE Corpus SYSTEM "ntumc.dtd">\n<Corpus')
        for name, value in attrs.items():
            if value:
                fh.write(f"\n        {name}={quoteattr(clean(value))}")
        fh.write(">\n")
        for db in opts.dbs:
            for lang, el, ids in iter_documents(db, opts.docs, opts.collections):
                ET.indent(el, level=1)
                fh.write("  " + ET.tostring(el, encoding="unicode") + "\n")
                dumped[lang].update(ids)
                counts[lang] += 1
        if opts.links:
            al = alignment_element(opts.links, dumped)
            if len(al):
                ET.indent(al, level=1)
                fh.write("  " + ET.tostring(al, encoding="unicode") + "\n")
                counts["alignments"] = len(al)
        fh.write("</Corpus>\n")
    shutil.copy(DTD, out.parent / DTD.name)
    return dict(counts)


# ---------------------------------------------------------------------------
# load: XML -> database
# ---------------------------------------------------------------------------


# Where each kind of within-sentence id lives: letter -> (table, id column).
SUB_TABLES = {"w": ("word", "wid"), "c": ("concept", "cid"), "x": ("chunks", "xid")}


class LoadError(Exception):
    """A problem in the XML that stops the load."""


@dataclass
class LangDB:
    """An open per-language database and its id counters."""

    con: sqlite3.Connection
    next_docid: int
    next_sid: int
    has_genre: bool
    corpora: dict[str, int]


@dataclass
class LoadOptions:
    """How ``Loader`` assigns ids and fills in missing values.

    Attributes:
        renumber: Always assign fresh document and sentence ids
        skip_existing: Pass over documents already in the database (same
            docid and sids) but still let alignments refer to their ids
        user: ``usrname`` for rows whose element has no ``last_changed_by``
        schema: SQL file for new language databases
        link_schema: SQL file for new link databases
    """

    renumber: bool = False
    skip_existing: bool = False
    user: str | None = None
    schema: Path = SCHEMA
    link_schema: Path = LINK_SCHEMA


class Loader:
    """Load NTU-MC XML into per-language and link databases.

    Args:
        outdir: Directory for ``LANG.db`` and ``FLANG-TLANG.db`` files
        opts: Id and default settings (see ``LoadOptions``)
    """

    def __init__(self, outdir: Path, opts: LoadOptions | None = None) -> None:
        self.outdir = outdir
        opts = opts or LoadOptions()
        self.renumber = opts.renumber
        self.skip_existing = opts.skip_existing
        self.user = opts.user
        self.schema = opts.schema
        self.link_schema = opts.link_schema
        self.corpus_attrs: dict[str, str] = {}
        self.langs: dict[str, LangDB] = {}
        self.links: dict[tuple[str, str], sqlite3.Connection] = {}
        self.doc_map: dict[str, tuple[str, int]] = {}
        self.sent_map: dict[str, tuple[str, int]] = {}
        # Only word/concept/chunk ids that do not have the form <sid-id><letter><n>
        self.sub_map: dict[str, tuple[str, int, int]] = {}
        self.counts: dict[str, int] = defaultdict(int)

    # -- databases ---------------------------------------------------------

    def lang_db(self, lang: str) -> LangDB:
        """Open (creating if needed) the database for a language."""
        if lang in self.langs:
            return self.langs[lang]
        path = self.outdir / f"{lang}.db"
        new = not path.exists()
        con = sqlite3.connect(path)
        if new:
            con.executescript(self.schema.read_text())
            con.execute(
                "INSERT INTO meta (title, license, lang, version) VALUES (?, ?, ?, ?)",
                (
                    self.corpus_attrs.get("title"),
                    self.corpus_attrs.get("license"),
                    lang,
                    self.corpus_attrs.get("version"),
                ),
            )
        ldb = LangDB(
            con=con,
            next_docid=(
                con.execute("SELECT COALESCE(MAX(docid), 0) + 1 FROM doc").fetchone()[0]
            ),
            next_sid=(
                con.execute("SELECT COALESCE(MAX(sid), 0) + 1 FROM sent").fetchone()[0]
            ),
            has_genre=has_column(con, "corpus", "genre"),
            corpora={
                r[0]: r[1] for r in con.execute("SELECT corpus, corpusID FROM corpus")
            },
        )
        self.langs[lang] = ldb
        return ldb

    def link_db(self, flang: str, tlang: str) -> sqlite3.Connection:
        """Open (creating if needed) the link database for a language pair."""
        key = (flang, tlang)
        if key in self.links:
            return self.links[key]
        path = self.outdir / f"{flang}-{tlang}.db"
        new = not path.exists()
        con = sqlite3.connect(path)
        if new:
            con.executescript(self.link_schema.read_text())
            con.execute(
                "INSERT INTO meta (fcorpus, flang, tcorpus, tlang) VALUES (?, ?, ?, ?)",
                (f"{flang}.db", flang, f"{tlang}.db", tlang),
            )
        self.links[key] = con
        return con

    def corpus_id(self, lang: str, el: ET.Element) -> int:
        """Return the corpusID for a document's collection, adding a row if new.

        Raises:
            LoadError: If a new collection has no (valid) genre and the
                database requires one
        """
        ldb = self.lang_db(lang)
        short = el.get("collection") or self.corpus_attrs.get("corpusID") or "corpus"
        if short in ldb.corpora:
            return ldb.corpora[short]
        genre = el.get("genre")
        if ldb.has_genre and genre not in GENRES:
            raise LoadError(
                f"document {el.get('docID')}: new collection {short!r} needs a genre "
                f"attribute, one of {', '.join(GENRES)}"
            )
        corpus_id = ldb.con.execute(
            "SELECT COALESCE(MAX(corpusID), 0) + 1 FROM corpus"
        ).fetchone()[0]
        title = el.get("collection_title") or short
        if ldb.has_genre:
            ldb.con.execute(
                "INSERT INTO corpus (corpusID, corpus, title, language, genre) VALUES (?, ?, ?, ?, ?)",
                (corpus_id, short, title, lang, genre),
            )
        else:
            ldb.con.execute(
                "INSERT INTO corpus (corpusID, corpus, title, language) VALUES (?, ?, ?, ?)",
                (corpus_id, short, title, lang),
            )
        ldb.corpora[short] = corpus_id
        return corpus_id

    # -- ids ----------------------------------------------------------------

    def _number(
        self, ldb: LangDB, xmlid: str, table: str, column: str, counter: str
    ) -> int:
        """Pick the database id for a document or sentence.

        Keeps the trailing number of ``xmlid`` when allowed and free;
        otherwise takes the next free number.

        Raises:
            LoadError: If the number is already used and renumbering is off
        """
        m = _TAIL_NUM.search(xmlid)
        if self.renumber or not m:
            n = getattr(ldb, counter)
            setattr(ldb, counter, n + 1)
            return n
        n = int(m.group(1))
        if ldb.con.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ?", (n,)
        ).fetchone():
            raise LoadError(
                f"{xmlid}: {column} {n} already exists in the database; use --renumber"
            )
        setattr(ldb, counter, max(getattr(ldb, counter), n + 1))
        return n

    def new_docid(self, lang: str, xmlid: str) -> int:
        """Assign and record the docid for a ``<Document>``."""
        if xmlid in self.doc_map:
            raise LoadError(f"duplicate document id {xmlid}")
        docid = self._number(self.lang_db(lang), xmlid, "doc", "docid", "next_docid")
        self.doc_map[xmlid] = (lang, docid)
        return docid

    def new_sid(self, lang: str, xmlid: str) -> int:
        """Assign and record the sid for a ``<Sentence>``."""
        if xmlid in self.sent_map:
            raise LoadError(f"duplicate sentence id {xmlid}")
        sid = self._number(self.lang_db(lang), xmlid, "sent", "sid", "next_sid")
        self.sent_map[xmlid] = (lang, sid)
        return sid

    def sub_id(
        self, lang: str, sid: int, sent_xmlid: str, xmlid: str, letter: str, index: int
    ) -> int:
        """Pick the within-sentence number for a word, concept or chunk.

        Uses the trailing number of ids shaped ``<sentence id><letter><n>``;
        otherwise the element's position, recorded for later references.
        """
        m = re.fullmatch(re.escape(sent_xmlid) + letter + r"(\d+)", xmlid)
        if m:
            return int(m.group(1))
        if xmlid in self.sub_map:
            raise LoadError(f"duplicate id {xmlid}")
        self.sub_map[xmlid] = (lang, sid, index)
        return index

    def resolve_sub(self, xmlid: str, letter: str) -> tuple[str, int, int]:
        """Resolve a word/concept/chunk id reference to ``(lang, sid, n)``.

        Raises:
            LoadError: If the id was never defined
        """
        if xmlid in self.sub_map:
            return self.sub_map[xmlid]
        m = re.fullmatch(r"(.+)" + letter + r"(\d+)", xmlid)
        if m and m.group(1) in self.sent_map:
            lang, sid = self.sent_map[m.group(1)]
            n = int(m.group(2))
            table, column = SUB_TABLES[letter]
            found = (
                self.langs[lang]
                .con.execute(
                    f"SELECT 1 FROM {table} WHERE sid = ? AND {column} = ?", (sid, n)
                )
                .fetchone()
            )
            if found:
                return lang, sid, n
        raise LoadError(f"reference to unknown id {xmlid}")

    def resolve_sent(self, xmlid: str) -> tuple[str, int]:
        """Resolve a sentence id reference to ``(lang, sid)``."""
        if xmlid not in self.sent_map:
            raise LoadError(f"reference to unknown sentence id {xmlid}")
        return self.sent_map[xmlid]

    # -- loading ------------------------------------------------------------

    def run(self, xml_path: Path) -> dict[str, int]:
        """Load a file, committing every database at the end.

        Args:
            xml_path: The XML file

        Returns:
            Counts of documents, sentences, words, concepts and links loaded

        Raises:
            LoadError: On duplicate or dangling ids, or a missing genre
        """
        self.outdir.mkdir(parents=True, exist_ok=True)
        try:
            for event, el in ET.iterparse(xml_path, events=("start", "end")):
                if event == "start" and el.tag == "Corpus":
                    self.corpus_attrs = dict(el.attrib)
                elif event == "end" and el.tag == "Document":
                    self.load_document(el)
                    el.clear()
                elif event == "end" and el.tag == "Alignment":
                    self.load_alignment(el)
                    el.clear()
            for ldb in self.langs.values():
                ldb.con.commit()
            for con in self.links.values():
                con.commit()
        finally:
            for ldb in self.langs.values():
                ldb.con.close()
            for con in self.links.values():
                con.close()
        return dict(self.counts)

    def load_document(self, el: ET.Element) -> None:
        """Insert one ``<Document>`` and everything under it."""
        lang = el.get("language")
        if not lang:
            raise LoadError(f"document {el.get('docID')} has no language")
        ldb = self.lang_db(lang)
        if self.skip_existing and self.register_existing(lang, el):
            return
        corpus_id = self.corpus_id(lang, el)
        docid = self.new_docid(lang, el.get("docID", ""))
        ldb.con.execute(
            "INSERT INTO doc (docid, doc, title, url, subtitle, corpusID) VALUES (?, ?, ?, ?, ?, ?)",
            (
                docid,
                el.get("doc"),
                el.get("title"),
                el.get("url"),
                el.get("subtitle"),
                corpus_id,
            ),
        )
        self.counts[f"{lang} documents"] += 1
        for sel in el.findall("Sentence"):
            self.load_sentence(lang, ldb.con, docid, sel)

    def register_existing(self, lang: str, el: ET.Element) -> bool:
        """Record the ids of a document that is already in the database.

        Returns:
            True if the document's docid exists, in which case its sentence
            ids are registered (so alignments can refer to them) and the
            document is not loaded again

        Raises:
            LoadError: If the document exists but one of its sentences does not
        """
        ldb = self.lang_db(lang)
        xmlid = el.get("docID", "")
        m = _TAIL_NUM.search(xmlid)
        if (
            not m
            or not ldb.con.execute(
                "SELECT 1 FROM doc WHERE docid = ?", (int(m.group(1)),)
            ).fetchone()
        ):
            return False
        for sel in el.findall("Sentence"):
            sent_xmlid = sel.get("sid", "")
            ms = _TAIL_NUM.search(sent_xmlid)
            sid = int(ms.group(1)) if ms else None
            if (
                sid is None
                or not ldb.con.execute(
                    "SELECT 1 FROM sent WHERE sid = ?", (sid,)
                ).fetchone()
            ):
                raise LoadError(
                    f"{xmlid} exists but its sentence {sent_xmlid} does not"
                )
            self.sent_map[sent_xmlid] = (lang, sid)
        self.counts[f"{lang} documents skipped"] += 1
        return True

    def load_sentence(
        self, lang: str, con: sqlite3.Connection, docid: int, sel: ET.Element
    ) -> None:
        """Insert one ``<Sentence>`` with its words, concepts, chunks and tags."""
        sent_xmlid = sel.get("sid", "")
        sid = self.new_sid(lang, sent_xmlid)
        user = sel.get("last_changed_by") or self.user
        con.execute(
            "INSERT INTO sent (sid, docID, pid, sent, comment, usrname) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, docid, sel.get("pid"), sel.get("sent"), sel.get("comment"), user),
        )
        self.counts[f"{lang} sentences"] += 1
        for tag in sel.findall("Tag"):
            if tag.get("category") == "stype":
                con.execute(
                    "INSERT INTO stype (sid, stype, comment) VALUES (?, ?, ?)",
                    (sid, tag.get("value"), tag.get("comment")),
                )

        for i, wel in enumerate(sel.findall("Word")):
            wid = self.sub_id(lang, sid, sent_xmlid, wel.get("wid", ""), "w", i)
            con.execute(
                "INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    wid,
                    wel.get("surface_form"),
                    wel.get("pos") or wel.get("upos"),
                    wel.get("lemma"),
                    _int(wel.get("cfrom")),
                    _int(wel.get("cto")),
                    wel.get("comment"),
                    wel.get("last_changed_by") or self.user,
                ),
            )
            self.counts[f"{lang} words"] += 1

        for i, cel in enumerate(sel.findall("Concept")):
            cid = self.sub_id(lang, sid, sent_xmlid, cel.get("cid", ""), "c", i)
            tags = {t.get("category"): t for t in cel.findall("Tag")}
            cuser = cel.get("last_changed_by") or self.user
            con.execute(
                "INSERT INTO concept (sid, cid, clemma, tag, tags, comment, ntag, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    cid,
                    cel.get("clemma"),
                    cel.get("synset_tag"),
                    _value(tags.get("candidates")),
                    cel.get("comment"),
                    _value(tags.get("ne")),
                    cuser,
                ),
            )
            for ref in cel.get("wid", "").split():
                _, _, wid = self.resolve_sub(ref, "w")
                con.execute(
                    "INSERT INTO cwl (sid, wid, cid, usrname) VALUES (?, ?, ?, ?)",
                    (sid, wid, cid, cuser),
                )
            senti = tags.get("sentiment")
            if senti is not None:
                con.execute(
                    "INSERT INTO sentiment (sid, cid, score, username) VALUES (?, ?, ?, ?)",
                    (
                        sid,
                        cid,
                        _float(senti.get("value")),
                        senti.get("last_changed_by") or cuser,
                    ),
                )
            self.counts[f"{lang} concepts"] += 1

        for i, xel in enumerate(sel.findall("Chunk")):
            xid = self.sub_id(lang, sid, sent_xmlid, xel.get("chid", ""), "x", i)
            tags = {t.get("category"): t for t in xel.findall("Tag")}
            xuser = xel.get("last_changed_by") or self.user
            con.execute(
                "INSERT INTO chunks (sid, xid, score, comment, username) VALUES (?, ?, ?, ?, ?)",
                (
                    sid,
                    xid,
                    _float(_value(tags.get("sentiment"))),
                    xel.get("comment"),
                    xuser,
                ),
            )
            for ref in xel.get("wid", "").split():
                _, _, wid = self.resolve_sub(ref, "w")
                con.execute(
                    "INSERT INTO xwl (sid, wid, xid, username) VALUES (?, ?, ?, ?)",
                    (sid, wid, xid, xuser),
                )
            self.counts[f"{lang} chunks"] += 1

    def load_alignment(self, al: ET.Element) -> None:
        """Insert the ``<Alignment>`` links into the pair databases."""
        for el in al.findall("SentAlignment"):
            flang, fsid = self.resolve_sent(el.get("sid_from", ""))
            for ref in el.get("sid_to", "").split():
                tlang, tsid = self.resolve_sent(ref)
                self._insert_link(
                    flang, tlang, "slink", ("fsid", "tsid"), (fsid, tsid), el
                )
        for el in al.findall("WordAlignment"):
            flang, fsid, fwid = self.resolve_sub(el.get("wid_from", ""), "w")
            for ref in el.get("wid_to", "").split():
                tlang, tsid, twid = self.resolve_sub(ref, "w")
                self._insert_link(
                    flang,
                    tlang,
                    "wlink",
                    ("fsid", "fwid", "tsid", "twid"),
                    (fsid, fwid, tsid, twid),
                    el,
                )
        for el in al.findall("ConceptAlignment"):
            flang, fsid, fcid = self.resolve_sub(el.get("cid_from", ""), "c")
            for ref in el.get("cid_to", "").split():
                tlang, tsid, tcid = self.resolve_sub(ref, "c")
                self._insert_link(
                    flang,
                    tlang,
                    "clink",
                    ("fsid", "fcid", "tsid", "tcid"),
                    (fsid, fcid, tsid, tcid),
                    el,
                )

    def _insert_link(
        self,
        flang: str,
        tlang: str,
        table: str,
        columns: tuple[str, ...],
        values: tuple[int, ...],
        el: ET.Element,
    ) -> None:
        """Insert one row into a link table, creating the pair database if needed."""
        con = self.link_db(flang, tlang)
        ltype = el.get("ltype")
        if ltype is None and el.get("type") == "automatic":
            ltype = "automatic"
        cols = ", ".join(columns + ("ltype", "conf", "comment", "usrname"))
        marks = ", ".join("?" * (len(columns) + 4))
        con.execute(
            f"INSERT INTO {table} ({cols}) VALUES ({marks})",
            values
            + (
                ltype,
                _float(el.get("conf")),
                el.get("comment"),
                el.get("last_changed_by") or self.user,
            ),
        )
        self.counts[f"{flang}-{tlang} {table}"] += 1


def _value(tag: ET.Element | None) -> str | None:
    """Return a ``<Tag>``'s value, or None if there is no tag."""
    return None if tag is None else tag.get("value")


def _int(text: str | None) -> int | None:
    """Parse an optional integer attribute; non-numbers become None with a warning."""
    if text in (None, ""):
        return None
    try:
        return int(text)
    except ValueError:
        logger.warning("ignoring non-integer offset %r", text)
        return None


def _float(text: str | None) -> float | None:
    """Parse an optional float attribute."""
    return None if text in (None, "") else float(text)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def validate(xml_path: Path, dtd: Path = DTD) -> bool:
    """Validate a file against the DTD with xmllint.

    The file's DOCTYPE names ``ntumc.dtd``; a copy beside the file is used
    first, then the directory of ``dtd``, so the file need not have one.

    Args:
        xml_path: The XML file
        dtd: The DTD to validate against

    Returns:
        True if valid

    Raises:
        RuntimeError: If xmllint is not installed
    """
    if shutil.which("xmllint") is None:
        raise RuntimeError("xmllint is not installed (package libxml2-utils)")
    beside = xml_path.parent / dtd.name
    if beside.exists() and beside.read_bytes() != dtd.read_bytes():
        logger.warning("%s differs from %s and takes precedence", beside, dtd)
    res = subprocess.run(
        [
            "xmllint",
            "--noout",
            "--path",
            str(dtd.parent),
            "--valid",
            str(xml_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = res.stderr.strip().splitlines()
        logger.error("%s", "\n".join(lines[:10]))
        if len(lines) > 10:
            logger.error("... %d more lines", len(lines) - 10)
    return res.returncode == 0


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Arguments without the program name (default: sys.argv[1:])

    Returns:
        Exit status
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dump = sub.add_parser("dump", help="write XML from corpus databases")
    p_dump.add_argument("out", type=Path, help="XML file to write")
    p_dump.add_argument(
        "--db",
        type=Path,
        nargs="+",
        required=True,
        help="language databases (eng.db ...)",
    )
    p_dump.add_argument(
        "--link",
        type=Path,
        nargs="*",
        default=[],
        help="link databases (eng-jpn.db ...)",
    )
    p_dump.add_argument("--doc", nargs="*", help="only these document names")
    p_dump.add_argument(
        "--collection", nargs="*", help="only these sub-corpora (story, kc ...)"
    )
    p_dump.add_argument(
        "--corpus-id", default="ntumc", help="Corpus corpusID attribute"
    )
    p_dump.add_argument(
        "--title", help="Corpus title (default: meta.title of the first database)"
    )
    p_dump.add_argument("--license", help="Corpus license (default: meta.license)")
    p_dump.add_argument("--version", help="Corpus version (default: meta.version)")

    p_load = sub.add_parser("load", help="load XML into corpus databases")
    p_load.add_argument("xml", type=Path, help="XML file to read")
    p_load.add_argument(
        "--outdir",
        type=Path,
        required=True,
        help="directory for LANG.db and FLANG-TLANG.db",
    )
    p_load.add_argument(
        "--renumber", action="store_true", help="always assign fresh docids and sids"
    )
    p_load.add_argument(
        "--skip-existing",
        action="store_true",
        help="pass over documents already in the database; alignments may still refer to them",
    )
    p_load.add_argument("--user", help="usrname for rows without last_changed_by")
    p_load.add_argument(
        "--schema", type=Path, default=SCHEMA, help="schema for new language databases"
    )
    p_load.add_argument(
        "--link-schema",
        type=Path,
        default=LINK_SCHEMA,
        help="schema for new link databases",
    )
    p_load.add_argument(
        "--no-validate", action="store_true", help="skip DTD validation before loading"
    )

    p_val = sub.add_parser("validate", help="validate XML against the DTD")
    p_val.add_argument("xml", type=Path, help="XML file to check")
    p_val.add_argument("--dtd", type=Path, default=DTD, help="DTD file")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "dump":
        opts = DumpOptions(
            dbs=args.db,
            links=args.link,
            docs=set(args.doc) if args.doc else None,
            collections=set(args.collection) if args.collection else None,
            corpus_id=args.corpus_id,
            title=args.title,
            license=args.license,
            version=args.version,
        )
        counts = dump(args.out, opts)
        for key, n in sorted(counts.items()):
            print(f"{key}: {n}")
        return 0

    if args.command == "validate":
        ok = validate(args.xml, args.dtd)
        print(f"{args.xml}: {'valid' if ok else 'INVALID'}")
        return 0 if ok else 1

    if not args.no_validate and shutil.which("xmllint") and not validate(args.xml):
        logger.error("%s does not validate; fix it or pass --no-validate", args.xml)
        return 1
    loader = Loader(
        args.outdir,
        LoadOptions(
            args.renumber, args.skip_existing, args.user, args.schema, args.link_schema
        ),
    )
    try:
        counts = loader.run(args.xml)
    except LoadError as exc:
        logger.error("%s", exc)
        return 1
    for key, n in sorted(counts.items()):
        print(f"{key}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
