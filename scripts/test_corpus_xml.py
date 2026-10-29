#!/usr/bin/env python3
"""Tests for corpus_xml.py: NTU-MC XML dump and load.

Usage:
    .venv/bin/python -m pytest scripts/test_corpus_xml.py -v
"""

import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.corpus_xml import (
    DTD,
    DumpOptions,
    Loader,
    LoadError,
    LoadOptions,
    clean,
    dump,
    main,
    validate,
)

EXAMPLE = Path(__file__).resolve().parent.parent / "data" / "corpus_example.xml"
needs_xmllint = pytest.mark.skipif(
    shutil.which("xmllint") is None, reason="xmllint not installed"
)


def rows(db: Path, sql: str) -> list[tuple]:
    """Run a query against a database and return all rows."""
    con = sqlite3.connect(db)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def table_dump(db: Path, table: str, columns: str) -> set[tuple]:
    """Return the given columns of a table as a set of rows."""
    return set(rows(db, f"SELECT {columns} FROM {table}"))


@pytest.fixture
def loaded(tmp_path: Path) -> Path:
    """Load the example corpus into a fresh directory and return it."""
    outdir = tmp_path / "db"
    Loader(outdir, LoadOptions(user="import")).run(EXAMPLE)
    return outdir


def test_clean_strips_control_characters() -> None:
    assert clean("a\x00b\x01c\td") == "abc\td"
    assert clean(None) is None


def test_load_example_creates_language_and_link_databases(loaded: Path) -> None:
    assert sorted(p.name for p in loaded.iterdir()) == [
        "eng-ita.db",
        "eng-spa.db",
        "eng.db",
        "ita.db",
        "spa.db",
    ]
    assert rows(
        loaded / "eng.db", "SELECT title, license, lang, version FROM meta"
    ) == [("Example of a multilingual corpus", "CC BY 4.0", "eng", "2026-10")]
    assert rows(
        loaded / "eng.db", "SELECT corpusID, corpus, title, language, genre FROM corpus"
    ) == [(1, "story", "Short Stories", "eng", "fiction")]
    assert rows(loaded / "eng.db", "SELECT docid, doc, title, corpusID FROM doc") == [
        (1, "woman", "A title", 1)
    ]
    assert rows(
        loaded / "eng.db", "SELECT sid, docID, pid, sent, usrname FROM sent"
    ) == [(1, 1, "1", "The beautiful woman", "annotator")]
    assert rows(
        loaded / "eng.db",
        "SELECT sid, wid, word, pos, lemma, cfrom, cto FROM word ORDER BY wid",
    ) == [
        (1, 0, "The", "DT", "the", 0, 3),
        (1, 1, "beautiful", "JJ", "beautiful", 4, 13),
        (1, 2, "woman", "NN", "woman", 14, 19),
    ]
    assert rows(
        loaded / "eng.db", "SELECT sid, cid, clemma, tag FROM concept ORDER BY cid"
    ) == [
        (1, 0, "beautiful", "00217728-a"),
        (1, 1, "woman", "10787470-n"),
    ]
    assert rows(loaded / "eng.db", "SELECT sid, wid, cid FROM cwl ORDER BY cid") == [
        (1, 1, 0),
        (1, 2, 1),
    ]
    assert rows(
        loaded / "eng.db", "SELECT sid, cid, score, username FROM sentiment"
    ) == [(1, 1, 34.0, "annotator")]
    assert rows(loaded / "eng.db", "SELECT sid, xid, score FROM chunks") == [
        (1, 0, 60.0)
    ]
    assert rows(loaded / "eng.db", "SELECT sid, wid, xid FROM xwl ORDER BY wid") == [
        (1, 1, 0),
        (1, 2, 0),
    ]
    assert rows(loaded / "eng.db", "SELECT sid, stype FROM stype") == [(1, "p")]


def test_load_example_links(loaded: Path) -> None:
    link = loaded / "eng-ita.db"
    assert rows(link, "SELECT fcorpus, flang, tcorpus, tlang FROM meta") == [
        ("eng.db", "eng", "ita.db", "ita")
    ]
    assert rows(link, "SELECT fsid, tsid, ltype, conf FROM slink") == [
        (1, 1, None, 1.0)
    ]
    assert rows(link, "SELECT fsid, fwid, tsid, twid, ltype FROM wlink") == [
        (1, 2, 1, 2, "automatic")
    ]
    assert rows(link, "SELECT fsid, fcid, tsid, tcid, ltype FROM clink") == [
        (1, 1, 1, 1, "=")
    ]
    assert rows(loaded / "eng-spa.db", "SELECT fsid, fcid, tsid, tcid FROM clink") == [
        (1, 1, 1, 0)
    ]


@needs_xmllint
def test_example_validates() -> None:
    assert validate(EXAMPLE, DTD)


@needs_xmllint
def test_dump_validates_and_round_trips(loaded: Path, tmp_path: Path) -> None:
    out = tmp_path / "back.xml"
    dbs = [loaded / f"{lang}.db" for lang in ("eng", "ita", "spa")]
    links = [loaded / "eng-ita.db", loaded / "eng-spa.db"]

    counts = dump(out, DumpOptions(dbs=dbs, links=links))

    assert counts == {"eng": 1, "ita": 1, "spa": 1, "alignments": 6}
    assert (tmp_path / "ntumc.dtd").exists()
    assert validate(out, DTD)

    again = tmp_path / "again"
    Loader(again, LoadOptions(user="import")).run(out)
    checks = {
        "eng.db": [
            ("sent", "sid, docID, pid, sent, usrname"),
            ("word", "sid, wid, word, pos, lemma, cfrom, cto"),
            ("concept", "sid, cid, clemma, tag"),
            ("cwl", "sid, wid, cid"),
            ("sentiment", "sid, cid, score, username"),
            ("chunks", "sid, xid, score"),
            ("xwl", "sid, wid, xid"),
            ("stype", "sid, stype"),
            ("corpus", "corpusID, corpus, title, genre"),
        ],
        "eng-ita.db": [
            ("slink", "fsid, tsid, ltype, conf"),
            ("wlink", "fsid, fwid, tsid, twid, ltype"),
            ("clink", "fsid, fcid, tsid, tcid, ltype"),
        ],
    }
    for db, tables in checks.items():
        for table, columns in tables:
            assert table_dump(loaded / db, table, columns) == table_dump(
                again / db, table, columns
            ), (db, table)


def test_reload_without_renumber_is_refused(loaded: Path) -> None:
    with pytest.raises(LoadError, match="already exists"):
        Loader(loaded).run(EXAMPLE)


def test_reload_with_renumber_appends(loaded: Path) -> None:
    Loader(loaded, LoadOptions(renumber=True)).run(EXAMPLE)

    assert rows(loaded / "eng.db", "SELECT sid FROM sent ORDER BY sid") == [(1,), (2,)]
    assert rows(loaded / "eng.db", "SELECT docid FROM doc ORDER BY docid") == [
        (1,),
        (2,),
    ]
    # The second copy joins the existing collection rather than adding one.
    assert rows(loaded / "eng.db", "SELECT count(*) FROM corpus") == [(1,)]
    assert rows(
        loaded / "eng-ita.db", "SELECT fsid, tsid FROM slink ORDER BY fsid"
    ) == [(1, 1), (2, 2)]
    assert rows(
        loaded / "eng-ita.db", "SELECT fsid, fcid, tsid, tcid FROM clink ORDER BY fsid"
    ) == [
        (1, 1, 1, 1),
        (2, 1, 2, 1),
    ]


def test_skip_existing_keeps_alignments_to_old_documents(
    loaded: Path, tmp_path: Path
) -> None:
    xml = tmp_path / "fra.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Corpus corpusID="c" title="t" linguality="multilingual">
  <Document docID="eng-d1" doc="woman" language="eng" title="A title" collection="story" genre="fiction">
    <Sentence sid="eng-s1" sent="The beautiful woman">
      <Word wid="eng-s1w2" surface_form="woman"/>
      <Concept cid="eng-s1c1" wid="eng-s1w2" clemma="woman"/>
    </Sentence>
  </Document>
  <Document docID="fra-d1" doc="woman" language="fra" title="Un titre" collection="story" genre="fiction">
    <Sentence sid="fra-s1" sent="La belle femme">
      <Word wid="fra-s1w0" surface_form="La"/>
      <Word wid="fra-s1w1" surface_form="belle"/>
      <Word wid="fra-s1w2" surface_form="femme"/>
      <Concept cid="fra-s1c0" wid="fra-s1w2" clemma="femme" synset_tag="10787470-n"/>
    </Sentence>
  </Document>
  <Alignment>
    <SentAlignment sid_from="fra-s1" sid_to="eng-s1"/>
    <ConceptAlignment cid_from="fra-s1c0" cid_to="eng-s1c1" ltype="="/>
  </Alignment>
</Corpus>
"""
    )

    counts = Loader(loaded, LoadOptions(skip_existing=True)).run(xml)

    assert counts["eng documents skipped"] == 1
    assert counts["fra documents"] == 1
    assert rows(loaded / "eng.db", "SELECT count(*) FROM sent") == [(1,)]
    assert rows(loaded / "fra-eng.db", "SELECT fsid, tsid FROM slink") == [(1, 1)]
    assert rows(
        loaded / "fra-eng.db", "SELECT fsid, fcid, tsid, tcid, ltype FROM clink"
    ) == [(1, 0, 1, 1, "=")]


def test_ids_without_numbers_get_positions(tmp_path: Path) -> None:
    xml = tmp_path / "plain.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Corpus corpusID="c" title="t" linguality="monolingual">
  <Document docID="doc" doc="x" language="fra" title="t" collection="story" genre="fiction">
    <Sentence sid="first" sent="Le chien">
      <Word wid="a" surface_form="Le" lemma="le"/>
      <Word wid="b" surface_form="chien" lemma="chien"/>
      <Concept cid="dog" wid="b" clemma="chien" synset_tag="02084071-n"/>
    </Sentence>
    <Sentence sid="second" sent="Il dort">
      <Word wid="c" surface_form="Il"/>
      <Word wid="d" surface_form="dort"/>
    </Sentence>
  </Document>
</Corpus>
"""
    )

    Loader(tmp_path / "db").run(xml)

    db = tmp_path / "db" / "fra.db"
    assert rows(db, "SELECT sid FROM sent ORDER BY sid") == [(1,), (2,)]
    assert rows(db, "SELECT sid, wid, word FROM word ORDER BY sid, wid") == [
        (1, 0, "Le"),
        (1, 1, "chien"),
        (2, 0, "Il"),
        (2, 1, "dort"),
    ]
    assert rows(db, "SELECT sid, wid, cid FROM cwl") == [(1, 1, 0)]


def test_new_collection_needs_genre(tmp_path: Path) -> None:
    xml = tmp_path / "nogenre.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Corpus corpusID="c" title="t" linguality="monolingual">
  <Document docID="d1" doc="x" language="fra" title="t" collection="story">
    <Sentence sid="s1" sent="Oui"><Word wid="s1w0" surface_form="Oui"/></Sentence>
  </Document>
</Corpus>
"""
    )
    with pytest.raises(LoadError, match="genre"):
        Loader(tmp_path / "db").run(xml)


def test_unknown_reference_is_an_error(tmp_path: Path) -> None:
    xml = tmp_path / "dangling.xml"
    xml.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Corpus corpusID="c" title="t" linguality="monolingual">
  <Document docID="d1" doc="x" language="fra" title="t" collection="story" genre="fiction">
    <Sentence sid="s1" sent="Oui">
      <Word wid="s1w0" surface_form="Oui"/>
      <Concept cid="s1c0" wid="s1w9" clemma="oui"/>
    </Sentence>
  </Document>
</Corpus>
"""
    )
    with pytest.raises(LoadError, match="unknown id s1w9"):
        Loader(tmp_path / "db").run(xml)


def test_dump_leaves_out_dangling_links(loaded: Path, tmp_path: Path) -> None:
    con = sqlite3.connect(loaded / "eng-ita.db")
    con.execute("INSERT INTO clink (fsid, fcid, tsid, tcid) VALUES (1, 99, 1, 1)")
    con.commit()
    con.close()
    out = tmp_path / "out.xml"

    counts = dump(
        out,
        DumpOptions(
            dbs=[loaded / "eng.db", loaded / "ita.db"], links=[loaded / "eng-ita.db"]
        ),
    )

    assert counts["alignments"] == 3
    assert "eng-s1c99" not in out.read_text()


def test_dump_document_filter(loaded: Path, tmp_path: Path) -> None:
    out = tmp_path / "none.xml"

    counts = dump(out, DumpOptions(dbs=[loaded / "eng.db"], docs={"no-such-doc"}))

    assert counts == {}
    assert "<Document" not in out.read_text()


def test_cli_load_and_dump(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    outdir = tmp_path / "db"

    status = main(["load", str(EXAMPLE), "--outdir", str(outdir), "--no-validate"])

    assert status == 0
    assert "eng sentences: 1" in capsys.readouterr().out
    status = main(["dump", str(tmp_path / "x.xml"), "--db", str(outdir / "eng.db")])
    assert status == 0
    assert 'linguality="monolingual"' in (tmp_path / "x.xml").read_text()
