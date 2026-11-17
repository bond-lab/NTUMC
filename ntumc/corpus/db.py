"""Read corpus and link databases into model objects, one document at a time.

The language databases differ slightly (older ones lack
``concept.ntag``, some have no ``chunks`` table), so each query adapts
to the columns that exist.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from .index import Index
from .model import (
    Alignment,
    Chunk,
    Concept,
    ConceptLink,
    CorpusInfo,
    Document,
    Item,
    Sentence,
    SentLink,
    Word,
    WordLink,
)

logger = logging.getLogger(__name__)

# Columns read from each annotation table; absent ones come back as NULL.
TABLES = {
    "word": "sid, wid, word, pos, lemma, cfrom, cto, comment, usrname",
    "concept": "sid, cid, clemma, tag, tags, comment, ntag, usrname",
    "cwl": "sid, wid, cid",
    "sentiment": "sid, cid, score, username, usrname",
    "stype": "sid, stype, comment",
    "chunks": "sid, xid, score, comment, username",
    "xwl": "sid, wid, xid",
}
LINK_TABLES = {
    "slink": "fsid, tsid, ltype, conf, comment, usrname",
    "wlink": "fsid, fwid, tsid, twid, ltype, conf, comment, usrname",
    "clink": "fsid, fcid, tsid, tcid, ltype, conf, comment, usrname",
}
_LISTS = {"slink": "sents", "wlink": "words", "clink": "concepts"}


@dataclass
class Selection:
    """Which documents to read: all, or those named, or those collections."""

    docs: set[str] = field(default_factory=set)
    collections: set[str] = field(default_factory=set)

    def sql(self) -> tuple[str, tuple]:
        """WHERE clause (on ``doc d`` joined to ``corpus c``) and parameters."""
        clauses, params = [], []
        if self.docs:
            clauses.append(f"d.doc IN ({','.join('?' * len(self.docs))})")
            params.extend(sorted(self.docs))
        if self.collections:
            clauses.append(f"c.corpus IN ({','.join('?' * len(self.collections))})")
            params.extend(sorted(self.collections))
        return (" OR ".join(clauses) or "1"), tuple(params)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a database read-only with named rows.

    Args:
        path: the database file

    Returns:
        The connection
    """
    con = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def db_lang(path: Path | str) -> str:
    """Return the language of a corpus database: ``meta.lang`` or the file stem.

    Args:
        path: the database file

    Returns:
        The language code
    """
    con = connect(path)
    try:
        row = con.execute("SELECT lang FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    return row[0] if row and row[0] else Path(path).stem


def link_langs(path: Path | str) -> tuple[str, str]:
    """Return the (from, to) languages of a link database.

    Args:
        path: a link database such as ``eng-jpn.db``

    Returns:
        From ``meta`` if present, else from the file name

    Raises:
        ValueError: if neither gives two languages
    """
    con = connect(path)
    try:
        row = con.execute("SELECT flang, tlang FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    if row and row[0] and row[1]:
        return row[0], row[1]
    parts = Path(path).stem.split("-")
    if len(parts) != 2:
        raise ValueError(f"cannot tell the languages of {path}; add a meta row")
    return parts[0], parts[1]


def read_info(path: Path | str) -> CorpusInfo:
    """Return the ``meta`` row of a corpus database.

    Args:
        path: the database file

    Returns:
        Title, license and version (all None if there is no meta row)
    """
    con = connect(path)
    try:
        row = con.execute("SELECT title, license, version FROM meta").fetchone()
    except sqlite3.OperationalError:
        row = None
    finally:
        con.close()
    if not row:
        return CorpusInfo()
    return CorpusInfo(title=row[0], license=row[1], version=row[2])


def _select(con: sqlite3.Connection, table: str, wanted: str) -> str | None:
    present = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    if not present:
        return None
    cols = [c.strip() for c in wanted.split(",")]
    return ", ".join(c if c in present else f"NULL AS {c}" for c in cols)


def _doc_rows(
    con: sqlite3.Connection, table: str, docid: int
) -> dict[int, list[sqlite3.Row]]:
    select = _select(con, table, TABLES[table])
    out: dict[int, list[sqlite3.Row]] = defaultdict(list)
    if select is None:
        return out
    rows = con.execute(
        f"SELECT {select} FROM {table} "
        "WHERE sid IN (SELECT sid FROM sent WHERE docID = ?)",
        (docid,),
    )
    for row in rows:
        out[row["sid"]].append(row)
    return out


def _candidates(tags: str | None) -> list[str]:
    if not tags:
        return []
    return [t.strip() for t in tags.split(";") if t.strip()]


def _sentence(
    sid_rows: dict[str, dict[int, list[sqlite3.Row]]], sent: sqlite3.Row
) -> Sentence:
    sid = sent["sid"]
    s = Sentence(
        sid,
        sent["sent"] or "",
        pid=_str(sent["pid"]),
        comment=_str(sent["comment"]),
        user=_str(sent["usrname"]),
    )
    for st in sid_rows["stype"].get(sid, [])[:1]:
        s.stype, s.stype_comment = _str(st["stype"]), _str(st["comment"])
    s.words = [
        Word(
            w["wid"],
            w["word"] or "",
            lemma=_str(w["lemma"]),
            pos=_str(w["pos"]),
            cfrom=_int(w["cfrom"]),
            cto=_int(w["cto"]),
            comment=_str(w["comment"]),
            user=_str(w["usrname"]),
        )
        for w in sorted(sid_rows["word"].get(sid, []), key=lambda r: r["wid"])
    ]
    cwl: dict[int, list[int]] = defaultdict(list)
    for r in sid_rows["cwl"].get(sid, []):
        cwl[r["cid"]].append(r["wid"])
    senti = {r["cid"]: r for r in sid_rows["sentiment"].get(sid, [])}
    for c in sorted(sid_rows["concept"].get(sid, []), key=lambda r: r["cid"]):
        cid = c["cid"]
        sc = senti.get(cid)
        s.concepts.append(
            Concept(
                cid,
                c["clemma"] or "",
                tag=_str(c["tag"]),
                wids=sorted(cwl.get(cid, [])),
                ne=_str(c["ntag"]),
                candidates=_candidates(c["tags"]),
                sentiment=sc["score"] if sc else None,
                sentiment_user=_str(sc["username"] or sc["usrname"]) if sc else None,
                comment=_str(c["comment"]),
                user=_str(c["usrname"]),
            )
        )
    xwl: dict[int, list[int]] = defaultdict(list)
    for r in sid_rows["xwl"].get(sid, []):
        xwl[r["xid"]].append(r["wid"])
    for x in sorted(sid_rows["chunks"].get(sid, []), key=lambda r: r["xid"]):
        s.chunks.append(
            Chunk(
                x["xid"],
                wids=sorted(xwl.get(x["xid"], [])),
                score=x["score"],
                comment=_str(x["comment"]),
                user=_str(x["username"]),
            )
        )
    return s


def _str(value: object) -> str | None:
    """Optional text columns: '' and None both mean absent."""
    return None if value is None or value == "" else str(value)


def _int(value: object) -> int | None:
    """Offsets are sometimes stored as '' or as text; keep only integers."""
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_document(con: sqlite3.Connection, lang: str, docid: int) -> Document:
    """Read one document with all its annotation.

    Args:
        con: connection from ``connect``
        lang: its language code
        docid: the document id

    Returns:
        The document

    Raises:
        KeyError: if there is no such docid
    """
    doc_cols = _select(con, "doc", "docid, doc, title, url, subtitle, corpusID")
    doc = con.execute(
        f"SELECT {doc_cols} FROM doc WHERE docid = ?", (docid,)
    ).fetchone()
    if doc is None:
        raise KeyError(f"no document {docid}")
    corpus_cols = _select(con, "corpus", "corpus, title, genre")
    corpus = con.execute(
        f"SELECT {corpus_cols} FROM corpus WHERE corpusID = ?", (doc["corpusID"],)
    ).fetchone()
    d = Document(
        doc["docid"],
        doc["doc"] or f"doc{docid}",
        lang,
        title=doc["title"] or "",
        subtitle=_str(doc["subtitle"]),
        url=_str(doc["url"]),
        collection=_str(corpus["corpus"]) if corpus else None,
        collection_title=_str(corpus["title"]) if corpus else None,
        genre=_str(corpus["genre"]) if corpus else None,
    )
    sid_rows = {t: _doc_rows(con, t, docid) for t in TABLES}
    sent_cols = _select(con, "sent", "sid, pid, sent, comment, usrname")
    sents = con.execute(
        f"SELECT {sent_cols} FROM sent WHERE docID = ? ORDER BY sid", (docid,)
    ).fetchall()
    d.sentences = [_sentence(sid_rows, s) for s in sents]
    return d


def read_documents(
    path: Path | str, select: Selection | None = None, lang: str | None = None
) -> Iterator[Document]:
    """Yield the documents of a corpus database in docid order.

    Args:
        path: the database file
        select: which documents (default all)
        lang: language code (default from the database)

    Yields:
        One Document at a time
    """
    lang = lang or db_lang(path)
    where, params = (select or Selection()).sql()
    con = connect(path)
    try:
        docids = [
            r[0]
            for r in con.execute(
                "SELECT d.docid FROM doc d LEFT JOIN corpus c ON c.corpusID = d.corpusID "
                f"WHERE {where} ORDER BY d.docid",
                params,
            )
        ]
        for docid in docids:
            yield read_document(con, lang, docid)
    finally:
        con.close()


def read_alignments(
    link_path: Path | str,
    from_path: Path | str,
    fdocs: Iterable[int] | None = None,
    index: Index | None = None,
) -> Iterator[Alignment]:
    """Yield the links of a link database grouped by from-side document.

    Args:
        link_path: the link database (eng-jpn.db)
        from_path: the corpus database of the from language, used to
            group the links by document
        fdocs: docids on the from side to include (default all)
        index: if given, only links whose two ends are in it are kept;
            the number left out is logged

    Yields:
        One Alignment per from-side document that has links
    """
    flang, tlang = link_langs(link_path)
    con = connect(link_path)
    con.execute("ATTACH ? AS f", (f"file:{Path(from_path)}?mode=ro",))
    present = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    docs = set(fdocs) if fdocs is not None else None
    groups: dict[int, Alignment] = {}
    skipped = 0
    for table, cols in LINK_TABLES.items():
        if table not in present:
            continue
        lcols = ", ".join(f"l.{c.strip()}" for c in cols.split(","))
        rows = con.execute(
            f"SELECT {lcols}, s.docID AS fdoc FROM {table} l "
            "LEFT JOIN f.sent s ON s.sid = l.fsid ORDER BY s.docID, l.fsid"
        )
        for r in rows:
            fdoc = r["fdoc"]
            if fdoc is None or (docs is not None and fdoc not in docs):
                continue
            common = {
                "ltype": r["ltype"] or None,
                "conf": r["conf"],
                "comment": r["comment"] or None,
                "user": r["usrname"] or None,
            }
            link: SentLink | WordLink | ConceptLink
            if table == "slink":
                link = SentLink(r["fsid"], r["tsid"], **common)
            elif table == "wlink":
                link = WordLink(r["fsid"], r["fwid"], r["tsid"], r["twid"], **common)
            else:
                link = ConceptLink(r["fsid"], r["fcid"], r["tsid"], r["tcid"], **common)
            if index is not None and not index.has_link(flang, tlang, link):
                skipped += 1
                continue
            a = groups.setdefault(fdoc, Alignment(flang, tlang, fdoc=fdoc))
            getattr(a, _LISTS[table]).append(link)
    con.close()
    if skipped:
        logger.warning(
            "%s: %d links left out (an end is not among the documents read)",
            link_path,
            skipped,
        )
    for fdoc in sorted(groups):
        yield groups[fdoc]


def read_corpus(
    dbs: Iterable[Path | str],
    links: Iterable[Path | str] = (),
    select: Selection | None = None,
) -> Iterator[Item]:
    """Stream a corpus: info, then every selected document, then the links.

    Only links whose two ends are among the selected documents are
    yielded, so the stream is self-contained.

    Args:
        dbs: corpus databases, one per language
        links: link databases between those languages
        select: which documents (default all)

    Yields:
        A CorpusInfo, then Documents, then Alignments
    """
    dbs = [Path(p) for p in dbs]
    by_lang: dict[str, Path] = {}
    docids: dict[str, list[int]] = defaultdict(list)
    index = Index()
    if dbs:
        yield read_info(dbs[0])
    for path in dbs:
        lang = db_lang(path)
        by_lang[lang] = path
        for doc in read_documents(path, select, lang):
            docids[lang].append(doc.docid)
            index.add(doc)
            yield doc
    for path in links:
        flang, tlang = link_langs(path)
        if flang not in by_lang or tlang not in by_lang:
            logger.warning("skipping %s: %s or %s not read", path, flang, tlang)
            continue
        yield from read_alignments(path, by_lang[flang], docids[flang], index)
