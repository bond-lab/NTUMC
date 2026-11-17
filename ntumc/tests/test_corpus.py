"""Tests for ntumc.corpus: model, database reader, JSON Lines and validator."""

import io
import sqlite3
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from ntumc.corpus import (
    Alignment,
    Concept,
    Corpus,
    CorpusError,
    CorpusInfo,
    Document,
    Sentence,
    SentLink,
    Word,
    db,
    dbwrite,
    jsonl,
    validate,
    xmlio,
)
from ntumc.corpus.__main__ import main

ROOT = Path(__file__).resolve().parents[2]


def _corpus_db(path: Path, lang: str, sents: dict[int, str]) -> None:
    con = sqlite3.connect(path)
    con.executescript((ROOT / "data" / "ntumc.sql").read_text())
    con.execute(
        "INSERT INTO meta (title, license, lang, version) VALUES ('T', 'CC', ?, '1')",
        (lang,),
    )
    con.execute(
        "INSERT INTO corpus (corpusID, corpus, title, language, genre) "
        "VALUES (1, 'story', 'Stories', ?, 'fiction')",
        (lang,),
    )
    con.execute(
        "INSERT INTO doc (docid, doc, title, corpusID) VALUES (1, 'cat', 'Cat', 1)"
    )
    for sid, text in sents.items():
        con.execute(
            "INSERT INTO sent (sid, docID, pid, sent, usrname) VALUES (?, 1, 'p1', ?, 'ann')",
            (sid, text),
        )
        pos = 0
        for wid, word in enumerate(text.split()):
            cfrom = text.index(word, pos)
            con.execute(
                "INSERT INTO word (sid, wid, word, lemma, pos, cfrom, cto) "
                "VALUES (?, ?, ?, ?, 'n', ?, ?)",
                (sid, wid, word, word.lower(), cfrom, cfrom + len(word)),
            )
            pos = cfrom + len(word)
            con.execute(
                "INSERT INTO concept (sid, cid, clemma, tag, tags, usrname) "
                "VALUES (?, ?, ?, '00000001-n', '00000001-n; 00000002-n', 'ann')",
                (sid, wid, word.lower()),
            )
            con.execute(
                "INSERT INTO cwl (sid, wid, cid) VALUES (?, ?, ?)", (sid, wid, wid)
            )
    con.execute("INSERT INTO stype (sid, stype) VALUES (1, 'h1')")
    con.execute(
        "INSERT INTO sentiment (sid, cid, score, username) VALUES (1, 0, 50, 'ann')"
    )
    con.execute("INSERT INTO chunks (sid, xid, score) VALUES (1, 0, -10)")
    con.execute("INSERT INTO xwl (sid, wid, xid) VALUES (1, 0, 0), (1, 1, 0)")
    con.commit()
    con.close()


@pytest.fixture
def build(tmp_path: Path) -> Path:
    """eng.db, xxx.db and eng-xxx.db with one document each."""
    _corpus_db(tmp_path / "eng.db", "eng", {1: "The cat", 2: "It sat"})
    _corpus_db(tmp_path / "xxx.db", "xxx", {10: "Le chat", 11: "Il sit"})
    con = sqlite3.connect(tmp_path / "eng-xxx.db")
    con.executescript((ROOT / "data" / "link.sql").read_text())
    con.execute(
        "INSERT INTO meta (fcorpus, flang, tcorpus, tlang) "
        "VALUES ('eng.db', 'eng', 'xxx.db', 'xxx')"
    )
    con.execute(
        "INSERT INTO slink (fsid, tsid, conf) VALUES (1, 10, 1.0), (2, 11, 0.5)"
    )
    con.execute("INSERT INTO wlink (fsid, fwid, tsid, twid) VALUES (1, 1, 10, 1)")
    con.execute(
        "INSERT INTO clink (fsid, fcid, tsid, tcid, ltype) VALUES (1, 1, 10, 1, '=')"
    )
    con.commit()
    con.close()
    return tmp_path


def test_read_documents(build: Path) -> None:
    docs = list(db.read_documents(build / "eng.db"))
    assert len(docs) == 1
    doc = docs[0]
    assert (doc.language, doc.doc, doc.collection, doc.genre) == (
        "eng",
        "cat",
        "story",
        "fiction",
    )
    s1 = doc.sentence(1)
    assert s1.text == "The cat"
    assert (s1.pid, s1.user, s1.stype) == ("p1", "ann", "h1")
    assert [(w.wid, w.word, w.cfrom, w.cto) for w in s1.words] == [
        (0, "The", 0, 3),
        (1, "cat", 4, 7),
    ]
    cat = s1.concept(1)
    assert cat == Concept(
        1,
        "cat",
        tag="00000001-n",
        wids=[1],
        candidates=["00000001-n", "00000002-n"],
        user="ann",
    )
    assert s1.concept(0).sentiment == 50
    assert s1.chunks[0].wids == [0, 1] and s1.chunks[0].score == -10
    assert [w.word for w in s1.words_of(cat)] == ["cat"]


def test_selection_and_missing_tables(build: Path) -> None:
    con = sqlite3.connect(build / "xxx.db")
    con.executescript(
        "DROP TABLE chunks; DROP TABLE xwl; "
        "DROP TRIGGER insert_concept_log; DROP TRIGGER update_concept_log; "
        "DROP TRIGGER delete_concept_log; ALTER TABLE concept DROP COLUMN ntag"
    )
    con.commit()
    con.close()
    assert [d.doc for d in db.read_documents(build / "xxx.db")] == ["cat"]
    assert list(db.read_documents(build / "xxx.db", db.Selection(docs={"dog"}))) == []
    assert (
        len(
            list(
                db.read_documents(build / "xxx.db", db.Selection(collections={"story"}))
            )
        )
        == 1
    )


def test_read_corpus_with_links(build: Path) -> None:
    items = list(
        db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    )
    assert items[0] == CorpusInfo(title="T", license="CC", version="1")
    assert [type(i).__name__ for i in items[1:]] == [
        "Document",
        "Document",
        "Alignment",
    ]
    a = items[3]
    assert (a.flang, a.tlang, a.fdoc) == ("eng", "xxx", 1)
    assert a.sents == [SentLink(1, 10, conf=1.0), SentLink(2, 11, conf=0.5)]
    assert a.words[0].twid == 1 and a.concepts[0].ltype == "="


def test_links_dropped_when_target_not_read(build: Path) -> None:
    con = sqlite3.connect(build / "eng-xxx.db")
    con.execute("INSERT INTO slink (fsid, tsid) VALUES (2, 99)")
    con.commit()
    con.close()
    items = list(
        db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    )
    assert [(s.fsid, s.tsid) for s in items[3].sents] == [(1, 10), (2, 11)]


def test_jsonl_roundtrip(build: Path) -> None:
    corpus = Corpus.from_items(
        db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    )
    buf = io.StringIO()
    assert jsonl.write(corpus, buf) == 4
    first = buf.getvalue().splitlines()[1]
    assert first.startswith('{"kind":"document","docid":1,"doc":"cat","language":"eng"')
    assert "null" not in first
    back = Corpus.from_items(jsonl.read(io.StringIO(buf.getvalue())))
    assert back == corpus


def test_jsonl_slim_drops_history(build: Path) -> None:
    corpus = Corpus.from_items(db.read_corpus([build / "eng.db"]))
    line = jsonl.dumps(corpus.documents[0], slim=True)
    assert "candidates" not in line and '"user"' not in line
    assert "00000001-n" in line
    doc = jsonl.loads(line)
    assert doc.sentence(1).concept(1).candidates == []


def test_loads_rejects_unknown(build: Path) -> None:
    with pytest.raises(ValueError):
        jsonl.loads(
            '{"kind":"document","docid":1,"doc":"d","language":"eng","colour":1}'
        )
    with pytest.raises(ValueError):
        jsonl.loads('{"docid":1}')


def test_corpus_lookups(build: Path) -> None:
    corpus = Corpus.from_items(
        db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    )
    assert corpus.languages == ["eng", "xxx"]
    assert corpus.document("eng", "cat") is corpus.document("eng", 1)
    assert corpus.sentence("xxx", 11).text == "Il sit"
    assert [(lang, link.tsid) for lang, link in corpus.links_from("eng", 1)] == [
        ("xxx", 10)
    ]
    assert [(lang, link.fsid) for lang, link in corpus.links_to("xxx", 11)] == [
        ("eng", 2)
    ]
    with pytest.raises(KeyError):
        corpus.document("eng", "dog")


def test_validate_clean(build: Path) -> None:
    items = db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    assert list(validate(items)) == []


def test_validate_finds_problems() -> None:
    s = Sentence(
        1,
        "The cat",
        words=[Word(0, "The", cfrom=0, cto=3), Word(1, "cat", cfrom=4, cto=6)],
        concepts=[
            Concept(1, "cat", tag="cat", wids=[1, 7]),
            Concept(2, "the", tag="00000001-n", wids=[]),
        ],
    )
    doc = Document(1, "cat", "eng", genre="poem", sentences=[s])
    align = Alignment("eng", "xxx", sents=[SentLink(1, 10)])
    codes = sorted(p.code for p in validate([doc, align]))
    assert codes == [
        "bad-wid",
        "cid-base",
        "genre",
        "link-sent",
        "no-words",
        "offset",
        "tag",
    ]
    levels = {p.code: p.level for p in validate([doc, align])}
    assert levels["bad-wid"] == "error" and levels["offset"] == "warning"


def test_cli_dump_and_validate(build: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = build / "out.jsonl"
    assert (
        main(
            [
                "dump",
                str(out),
                "--db",
                str(build / "eng.db"),
                str(build / "xxx.db"),
                "--link",
                str(build / "eng-xxx.db"),
            ]
        )
        == 0
    )
    assert len(out.read_text().splitlines()) == 4
    assert main(["validate", str(out)]) == 0
    assert capsys.readouterr().out.strip().endswith("0 errors, 0 warnings")
    out.write_text(out.read_text().replace('"tsid":10', '"tsid":99'))
    assert main(["validate", str(out)]) == 1


EXAMPLE = ROOT / "data" / "corpus_example.xml"


def test_xml_read_example() -> None:
    corpus = Corpus.from_items(xmlio.read(EXAMPLE))
    assert corpus.info.title == "Example of a multilingual corpus"
    assert corpus.languages == ["eng", "ita", "spa"]
    eng = corpus.document("eng", "woman")
    assert (eng.docid, eng.collection, eng.collection_title, eng.genre) == (
        1,
        "story",
        "Short Stories",
        "fiction",
    )
    s = eng.sentence(1)
    assert s.stype == "p" and s.user == "annotator"
    assert s.concept(1).sentiment == 34 and s.concept(1).sentiment_user == "annotator"
    assert s.chunks[0].wids == [1, 2] and s.chunks[0].score == 60
    assert [(a.tlang, a.fdoc, len(a)) for a in corpus.alignments] == [
        ("ita", 1, 3),
        ("spa", 1, 3),
    ]
    assert corpus.alignments[0].words[0].ltype == "automatic"
    assert list(validate(corpus)) == []


def test_xml_write_read_roundtrip(build: Path, tmp_path: Path) -> None:
    corpus = Corpus.from_items(
        db.read_corpus([build / "eng.db", build / "xxx.db"], [build / "eng-xxx.db"])
    )
    out = tmp_path / "out.xml"
    counts = xmlio.write(corpus, out, xmlio.XMLOptions(linguality="multilingual"))
    assert counts == {"eng": 1, "xxx": 1, "alignments": 4}
    assert (tmp_path / "ntumc.dtd").exists()
    text = out.read_text()
    assert 'sid="eng-s1"' in text and 'wid="eng-s1w1"' in text
    assert '<Tag category="candidates" value="00000001-n; 00000002-n"' in text
    assert Corpus.from_items(xmlio.read(out)) == corpus


def test_xml_ids_without_numbers_and_errors(tmp_path: Path) -> None:
    xml = tmp_path / "plain.xml"
    xml.write_text(
        """<Corpus corpusID="c" title="t" linguality="monolingual">
  <Document docID="doc" doc="x" language="fra" title="t" genre="fiction">
    <Sentence sid="first" sent="Le chien">
      <Word wid="a" surface_form="Le" upos="DET"/>
      <Word wid="b" surface_form="chien"/>
      <Concept cid="dog" wid="b" clemma="chien" synset_tag="02084071-n"/>
    </Sentence>
    <Sentence sid="second" sent="Il dort"><Word wid="c" surface_form="Il"/></Sentence>
  </Document>
</Corpus>
"""
    )
    doc = next(d for d in xmlio.read(xml) if isinstance(d, Document))
    assert doc.docid == 1 and doc.collection == "c"
    assert [s.sid for s in doc] == [1, 2]
    assert doc.sentence(1).words[0].pos == "DET"
    assert doc.sentence(1).concept(0).wids == [1]
    xml.write_text(xml.read_text().replace('wid="b" clemma', 'wid="zz" clemma'))
    with pytest.raises(CorpusError, match="unknown id zz"):
        list(xmlio.read(xml))
    xml.write_text(xml.read_text().replace(' language="fra"', ""))
    with pytest.raises(CorpusError, match="no language"):
        list(xmlio.read(xml))


def test_dbwrite_then_read_back(tmp_path: Path) -> None:
    items = list(xmlio.read(EXAMPLE))
    out = tmp_path / "db"
    counts = dbwrite.write(items, out, dbwrite.WriteOptions(user="import"))
    assert counts["eng words"] == 3 and counts["eng-ita clink"] == 1
    back = Corpus.from_items(
        db.read_corpus(
            [out / "eng.db", out / "ita.db", out / "spa.db"],
            [out / "eng-ita.db", out / "eng-spa.db"],
        )
    )
    # the default user fills the rows that had none; everything else is the same
    for item in back:
        for obj in _walk(item):
            if getattr(obj, "user", None) == "import":
                obj.user = None
    assert back == Corpus.from_items(items)


def _walk(item: object) -> list[object]:
    out = [item]
    if is_dataclass(item):
        for f in fields(item):
            value = getattr(item, f.name)
            if isinstance(value, list):
                for child in value:
                    out.extend(_walk(child))
    return out


def test_dbwrite_refuses_then_renumbers(tmp_path: Path) -> None:
    out = tmp_path / "db"
    dbwrite.write(xmlio.read(EXAMPLE), out)
    with pytest.raises(CorpusError, match="already exists"):
        dbwrite.write(xmlio.read(EXAMPLE), out)
    dbwrite.write(xmlio.read(EXAMPLE), out, dbwrite.WriteOptions(renumber=True))
    con = sqlite3.connect(out / "eng-ita.db")
    assert con.execute("SELECT fsid, tsid FROM slink ORDER BY fsid").fetchall() == [
        (1, 1),
        (2, 2),
    ]
    with pytest.raises(CorpusError, match="not written"):
        dbwrite.write([Alignment("eng", "ita", sents=[SentLink(9, 1)])], out)


def test_cli_convert_and_load(build: Path, tmp_path: Path) -> None:
    jl, xml, out = tmp_path / "c.jsonl", tmp_path / "c.xml", tmp_path / "db"
    dbs = [str(build / "eng.db"), str(build / "xxx.db")]
    assert (
        main(["dump", str(jl), "--db", *dbs, "--link", str(build / "eng-xxx.db")]) == 0
    )
    assert main(["convert", str(jl), str(xml)]) == 0
    assert main(["validate", str(xml)]) == 0
    assert main(["load", str(xml), "--outdir", str(out), "--user", "u"]) == 0
    assert (out / "eng-xxx.db").exists()
    assert main(["convert", str(jl), str(tmp_path / "c.txt")]) == 1
