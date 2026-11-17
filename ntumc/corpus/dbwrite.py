"""Write model items into per-language and link SQLite databases.

``Writer`` creates ``LANG.db`` and ``FLANG-TLANG.db`` files in a
directory (from ``data/ntumc.sql`` and ``data/link.sql``) or appends to
the ones there.  Document and sentence ids are kept when they are free;
with ``renumber`` they are always reassigned, and the alignments that
follow are mapped accordingly.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .model import (
    GENRES,
    Alignment,
    CorpusError,
    CorpusInfo,
    Document,
    Item,
    Sentence,
)

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "data" / "ntumc.sql"
LINK_SCHEMA = REPO / "data" / "link.sql"


@dataclass
class WriteOptions:
    """How ids are assigned and missing values filled in.

    Attributes:
        renumber: Always assign fresh document and sentence ids
        skip_existing: Pass over documents already in the database (same
            docid and sids) but still let alignments refer to their ids
        user: ``usrname`` for rows that have no user
        schema: SQL file for new language databases
        link_schema: SQL file for new link databases
    """

    renumber: bool = False
    skip_existing: bool = False
    user: str | None = None
    schema: Path = SCHEMA
    link_schema: Path = LINK_SCHEMA


@dataclass
class _LangDB:
    con: sqlite3.Connection
    next_docid: int
    next_sid: int
    has_genre: bool
    corpora: dict[str, int]


class Writer:
    """Write items to the databases in a directory; commit on ``close``.

    Args:
        outdir: Directory for ``LANG.db`` and ``FLANG-TLANG.db`` files
        opts: Id and default settings
    """

    def __init__(self, outdir: Path | str, opts: WriteOptions | None = None) -> None:
        self.outdir = Path(outdir)
        self.opts = opts or WriteOptions()
        self.info = CorpusInfo()
        self.langs: dict[str, _LangDB] = {}
        self.links: dict[tuple[str, str], sqlite3.Connection] = {}
        # (lang, sid as it came in) -> sid in the database
        self.sid_map: dict[tuple[str, int], int] = {}
        self.counts: dict[str, int] = defaultdict(int)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close(commit=exc_type is None)

    def close(self, commit: bool = True) -> dict[str, int]:
        """Commit (or not) and close every database.

        Args:
            commit: Whether to keep what was written

        Returns:
            Counts of documents, sentences, words, concepts, chunks and links
        """
        for con in [ldb.con for ldb in self.langs.values()] + list(self.links.values()):
            if commit:
                con.commit()
            con.close()
        self.langs.clear()
        self.links.clear()
        return dict(self.counts)

    def add(self, item: Item) -> None:
        """Write one item.

        Args:
            item: CorpusInfo (used for the meta table of new databases),
                a Document or an Alignment

        Raises:
            CorpusError: On an id clash without renumber, a new collection
                without a genre, or a link to a sentence not written
        """
        if isinstance(item, CorpusInfo):
            self.info = item
        elif isinstance(item, Document):
            self._add_document(item)
        else:
            self._add_alignment(item)

    # -- databases ---------------------------------------------------------

    def _lang_db(self, lang: str) -> _LangDB:
        if lang in self.langs:
            return self.langs[lang]
        self.outdir.mkdir(parents=True, exist_ok=True)
        path = self.outdir / f"{lang}.db"
        new = not path.exists()
        # Foreign keys stay off: the schema's xwl/ewl references point at
        # non-unique columns and SQLite refuses every insert with them on.
        con = sqlite3.connect(path)
        if new:
            con.executescript(self.opts.schema.read_text())
            con.execute(
                "INSERT INTO meta (title, license, lang, version) VALUES (?, ?, ?, ?)",
                (self.info.title, self.info.license, lang, self.info.version),
            )
        has_genre = any(
            r[1] == "genre" for r in con.execute("PRAGMA table_info(corpus)")
        )
        ldb = _LangDB(
            con=con,
            next_docid=con.execute(
                "SELECT COALESCE(MAX(docid), 0) + 1 FROM doc"
            ).fetchone()[0],
            next_sid=con.execute(
                "SELECT COALESCE(MAX(sid), 0) + 1 FROM sent"
            ).fetchone()[0],
            has_genre=has_genre,
            corpora={
                r[0]: r[1] for r in con.execute("SELECT corpus, corpusID FROM corpus")
            },
        )
        self.langs[lang] = ldb
        return ldb

    def _link_db(self, flang: str, tlang: str) -> sqlite3.Connection:
        key = (flang, tlang)
        if key in self.links:
            return self.links[key]
        self.outdir.mkdir(parents=True, exist_ok=True)
        path = self.outdir / f"{flang}-{tlang}.db"
        new = not path.exists()
        con = sqlite3.connect(path)
        if new:
            con.executescript(self.opts.link_schema.read_text())
            con.execute(
                "INSERT INTO meta (fcorpus, flang, tcorpus, tlang) VALUES (?, ?, ?, ?)",
                (f"{flang}.db", flang, f"{tlang}.db", tlang),
            )
        self.links[key] = con
        return con

    def _corpus_id(self, ldb: _LangDB, doc: Document) -> int:
        short = doc.collection or "corpus"
        if short in ldb.corpora:
            return ldb.corpora[short]
        if ldb.has_genre and doc.genre not in GENRES:
            raise CorpusError(
                f"document {doc.language} d{doc.docid}: new collection {short!r} needs "
                f"a genre, one of {', '.join(GENRES)}"
            )
        corpus_id = ldb.con.execute(
            "SELECT COALESCE(MAX(corpusID), 0) + 1 FROM corpus"
        ).fetchone()[0]
        title = doc.collection_title or short
        if ldb.has_genre:
            ldb.con.execute(
                "INSERT INTO corpus (corpusID, corpus, title, language, genre) "
                "VALUES (?, ?, ?, ?, ?)",
                (corpus_id, short, title, doc.language, doc.genre),
            )
        else:
            ldb.con.execute(
                "INSERT INTO corpus (corpusID, corpus, title, language) VALUES (?, ?, ?, ?)",
                (corpus_id, short, title, doc.language),
            )
        ldb.corpora[short] = corpus_id
        return corpus_id

    # -- ids ----------------------------------------------------------------

    def _number(self, ldb: _LangDB, n: int, table: str, column: str) -> int:
        """Keep ``n`` if allowed and free, else take the next free number."""
        counter = "next_docid" if table == "doc" else "next_sid"
        if self.opts.renumber:
            fresh = getattr(ldb, counter)
            setattr(ldb, counter, fresh + 1)
            return fresh
        if ldb.con.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ?", (n,)
        ).fetchone():
            raise CorpusError(
                f"{column} {n} already exists in the database; use --renumber"
            )
        setattr(ldb, counter, max(getattr(ldb, counter), n + 1))
        return n

    # -- documents ----------------------------------------------------------

    def _add_document(self, doc: Document) -> None:
        lang = doc.language
        ldb = self._lang_db(lang)
        if self.opts.skip_existing and self._register_existing(ldb, doc):
            return
        corpus_id = self._corpus_id(ldb, doc)
        docid = self._number(ldb, doc.docid, "doc", "docid")
        ldb.con.execute(
            "INSERT INTO doc (docid, doc, title, url, subtitle, corpusID) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (docid, doc.doc, doc.title, doc.url, doc.subtitle, corpus_id),
        )
        self.counts[f"{lang} documents"] += 1
        for s in doc.sentences:
            self._add_sentence(ldb, lang, docid, s)

    def _register_existing(self, ldb: _LangDB, doc: Document) -> bool:
        """Record the sids of a document already in the database; True if it is."""
        if not ldb.con.execute(
            "SELECT 1 FROM doc WHERE docid = ?", (doc.docid,)
        ).fetchone():
            return False
        for s in doc.sentences:
            if not ldb.con.execute(
                "SELECT 1 FROM sent WHERE sid = ?", (s.sid,)
            ).fetchone():
                raise CorpusError(
                    f"document {doc.language} d{doc.docid} exists but its sentence "
                    f"s{s.sid} does not"
                )
            self.sid_map[(doc.language, s.sid)] = s.sid
        self.counts[f"{doc.language} documents skipped"] += 1
        return True

    def _add_sentence(self, ldb: _LangDB, lang: str, docid: int, s: Sentence) -> None:
        con = ldb.con
        sid = self._number(ldb, s.sid, "sent", "sid")
        self.sid_map[(lang, s.sid)] = sid
        user = self.opts.user
        con.execute(
            "INSERT INTO sent (sid, docID, pid, sent, comment, usrname) VALUES (?, ?, ?, ?, ?, ?)",
            (sid, docid, s.pid, s.text, s.comment, s.user or user),
        )
        self.counts[f"{lang} sentences"] += 1
        if s.stype:
            con.execute(
                "INSERT INTO stype (sid, stype, comment) VALUES (?, ?, ?)",
                (sid, s.stype, s.stype_comment),
            )
        con.executemany(
            "INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    sid,
                    w.wid,
                    w.word,
                    w.pos,
                    w.lemma,
                    w.cfrom,
                    w.cto,
                    w.comment,
                    w.user or user,
                )
                for w in s.words
            ],
        )
        self.counts[f"{lang} words"] += len(s.words)
        for c in s.concepts:
            cuser = c.user or user
            con.execute(
                "INSERT INTO concept (sid, cid, clemma, tag, tags, comment, ntag, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sid,
                    c.cid,
                    c.clemma,
                    c.tag,
                    "; ".join(c.candidates) or None,
                    c.comment,
                    c.ne,
                    cuser,
                ),
            )
            con.executemany(
                "INSERT INTO cwl (sid, wid, cid, usrname) VALUES (?, ?, ?, ?)",
                [(sid, wid, c.cid, cuser) for wid in c.wids],
            )
            if c.sentiment is not None:
                con.execute(
                    "INSERT INTO sentiment (sid, cid, score, username) VALUES (?, ?, ?, ?)",
                    (sid, c.cid, c.sentiment, c.sentiment_user or cuser),
                )
        self.counts[f"{lang} concepts"] += len(s.concepts)
        for x in s.chunks:
            xuser = x.user or user
            con.execute(
                "INSERT INTO chunks (sid, xid, score, comment, username) VALUES (?, ?, ?, ?, ?)",
                (sid, x.xid, x.score, x.comment, xuser),
            )
            con.executemany(
                "INSERT INTO xwl (sid, wid, xid, username) VALUES (?, ?, ?, ?)",
                [(sid, wid, x.xid, xuser) for wid in x.wids],
            )
        self.counts[f"{lang} chunks"] += len(s.chunks)

    # -- alignments ---------------------------------------------------------

    def _sid(self, lang: str, sid: int) -> int:
        try:
            return self.sid_map[(lang, sid)]
        except KeyError:
            raise CorpusError(
                f"link to sentence {lang} s{sid}, which was not written"
            ) from None

    def _check(self, lang: str, sid: int, table: str, column: str, n: int) -> None:
        con = self._lang_db(lang).con
        if not con.execute(
            f"SELECT 1 FROM {table} WHERE sid = ? AND {column} = ?", (sid, n)
        ).fetchone():
            raise CorpusError(
                f"link to {table} {lang} s{sid} {column} {n}, which does not exist"
            )

    def _add_alignment(self, a: Alignment) -> None:
        con = self._link_db(a.flang, a.tlang)
        key = f"{a.flang}-{a.tlang}"
        for link in a.sents:
            fsid, tsid = self._sid(a.flang, link.fsid), self._sid(a.tlang, link.tsid)
            con.execute(
                "INSERT INTO slink (fsid, tsid, ltype, conf, comment, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    fsid,
                    tsid,
                    link.ltype,
                    link.conf,
                    link.comment,
                    link.user or self.opts.user,
                ),
            )
            self.counts[f"{key} slink"] += 1
        for link in a.words:
            fsid, tsid = self._sid(a.flang, link.fsid), self._sid(a.tlang, link.tsid)
            self._check(a.flang, fsid, "word", "wid", link.fwid)
            self._check(a.tlang, tsid, "word", "wid", link.twid)
            con.execute(
                "INSERT INTO wlink (fsid, fwid, tsid, twid, ltype, conf, comment, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fsid,
                    link.fwid,
                    tsid,
                    link.twid,
                    link.ltype,
                    link.conf,
                    link.comment,
                    link.user or self.opts.user,
                ),
            )
            self.counts[f"{key} wlink"] += 1
        for link in a.concepts:
            fsid, tsid = self._sid(a.flang, link.fsid), self._sid(a.tlang, link.tsid)
            self._check(a.flang, fsid, "concept", "cid", link.fcid)
            self._check(a.tlang, tsid, "concept", "cid", link.tcid)
            con.execute(
                "INSERT INTO clink (fsid, fcid, tsid, tcid, ltype, conf, comment, usrname) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fsid,
                    link.fcid,
                    tsid,
                    link.tcid,
                    link.ltype,
                    link.conf,
                    link.comment,
                    link.user or self.opts.user,
                ),
            )
            self.counts[f"{key} clink"] += 1


def write(
    items: Iterable[Item], outdir: Path | str, opts: WriteOptions | None = None
) -> dict[str, int]:
    """Write a stream of items to the databases in a directory.

    Nothing is committed if an item fails.

    Args:
        items: CorpusInfo, documents and alignments, documents first
        outdir: Directory for the databases
        opts: Id and default settings

    Returns:
        Counts of what was written

    Raises:
        CorpusError: see ``Writer.add``
    """
    with Writer(outdir, opts) as writer:
        for item in items:
            writer.add(item)
    return dict(writer.counts)
