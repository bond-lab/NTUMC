#!/usr/bin/env python3
"""Tests for make_display.py — static HTML corpus display generation.

Tests cover:
  - compute_nospace: spacing logic from cfrom/cto and fallback
  - build_concept_info: concept extraction and word_cids annotation
  - cross_compile_slinks: transitive slink computation
  - render_html: template rendering with correct variables
  - build_data_files: JSON data file generation (slinks, sentences, WN data)
  - write_document: end-to-end document generation

Usage:
    .venv/bin/python -m pytest scripts/test_make_display.py -v
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.make_display import (
    build_concept_info,
    build_data_files,
    compute_nospace,
    cross_compile_slinks,
    render_html,
    write_consolidated_json,
    write_doc_json,
    write_document,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _create_corpus_schema(conn: sqlite3.Connection, with_genre: bool = True) -> None:
    """Create the standard corpus schema, optionally without the genre column."""
    genre_col = (
        "genre TEXT NOT NULL CHECK (genre IN "
        "('essay','fiction','lexical','news','online','tourism'))"
        if with_genre else ""
    )
    corpus_cols = "corpusID INTEGER PRIMARY KEY, title TEXT, corpus TEXT"
    if genre_col:
        corpus_cols += ", " + genre_col
    conn.executescript(f"""
        CREATE TABLE corpus ({corpus_cols});
        CREATE TABLE doc (docid INTEGER PRIMARY KEY, doc TEXT, title TEXT,
                          subtitle TEXT, corpusID INTEGER);
        CREATE TABLE sent (sid INTEGER PRIMARY KEY, docID INTEGER,
                           sent TEXT, comment TEXT);
        CREATE TABLE stype (sid INTEGER PRIMARY KEY, stype TEXT);
        CREATE TABLE word (sid INTEGER, wid INTEGER, word TEXT,
                           pos TEXT, lemma TEXT, comment TEXT,
                           cfrom INTEGER, cto INTEGER,
                           PRIMARY KEY (sid, wid));
        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, comment TEXT);
        CREATE TABLE cwl (sid INTEGER, wid INTEGER, cid INTEGER,
                          PRIMARY KEY (sid, wid, cid));
        CREATE TABLE sentiment (sid INTEGER, cid INTEGER, score REAL,
                                comment TEXT, usrname TEXT,
                                PRIMARY KEY (sid, cid));
    """)


@pytest.fixture()
def tmp_outdir(tmp_path):
    """Create an output directory structure."""
    return tmp_path / "display"


@pytest.fixture()
def corpus_db(tmp_path):
    """Create a minimal corpus database for testing."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    _create_corpus_schema(conn)
    conn.executescript("""
        INSERT INTO corpus VALUES (1, 'Test Corpus', 'story', 'fiction');
        INSERT INTO doc VALUES (1, 'testdoc', 'Test Document', 'A test', 1);
        INSERT INTO sent VALUES (100, 1, 'The quick brown fox .', NULL);
        INSERT INTO sent VALUES (101, 1, 'It jumped over the fence .', NULL);
        INSERT INTO stype VALUES (100, 'p');
        INSERT INTO stype VALUES (101, NULL);
        INSERT INTO word VALUES (100, 0, 'The', 'DT', 'the', NULL, 0, 3);
        INSERT INTO word VALUES (100, 1, 'quick', 'JJ', 'quick', NULL, 4, 9);
        INSERT INTO word VALUES (100, 2, 'brown', 'JJ', 'brown', NULL, 10, 15);
        INSERT INTO word VALUES (100, 3, 'fox', 'NN', 'fox', NULL, 16, 19);
        INSERT INTO word VALUES (100, 4, '.', '.', '.', NULL, 20, 21);
        INSERT INTO word VALUES (101, 0, 'It', 'PRP', 'it', NULL, 0, 2);
        INSERT INTO word VALUES (101, 1, 'jumped', 'VBD', 'jump', NULL, 3, 9);
        INSERT INTO word VALUES (101, 2, 'over', 'IN', 'over', NULL, 10, 14);
        INSERT INTO word VALUES (101, 3, 'the', 'DT', 'the', NULL, 15, 18);
        INSERT INTO word VALUES (101, 4, 'fence', 'NN', 'fence', NULL, 19, 24);
        INSERT INTO word VALUES (101, 5, '.', '.', '.', NULL, 25, 26);
        INSERT INTO concept VALUES (100, 1, 'quick', '01068018-a', NULL);
        INSERT INTO concept VALUES (100, 2, 'brown fox', '02119022-n', NULL);
        INSERT INTO concept VALUES (101, 1, 'jump', '01965856-v', NULL);
        INSERT INTO concept VALUES (101, 2, 'fence', '03326073-n', NULL);
        INSERT INTO concept VALUES (101, 3, 'skip', 'x', NULL);
        INSERT INTO cwl VALUES (100, 1, 1);
        INSERT INTO cwl VALUES (100, 2, 2);
        INSERT INTO cwl VALUES (100, 3, 2);
        INSERT INTO cwl VALUES (101, 1, 1);
        INSERT INTO cwl VALUES (101, 4, 2);
        INSERT INTO cwl VALUES (101, 1, 3);
    """)
    conn.close()
    return db_path


@pytest.fixture()
def wn_db(tmp_path):
    """Create a minimal WordNet database for testing."""
    db_path = tmp_path / "wn-ntumc.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE synset (synset TEXT PRIMARY KEY, pos TEXT);
        INSERT INTO synset VALUES ('01068018-a', 'a');
        INSERT INTO synset VALUES ('02119022-n', 'n');
        INSERT INTO synset VALUES ('01965856-v', 'v');
        INSERT INTO synset VALUES ('03326073-n', 'n');

        CREATE TABLE synset_def (sid INTEGER PRIMARY KEY, synset TEXT,
                                 def TEXT, lang TEXT);
        INSERT INTO synset_def VALUES (1, '01068018-a', 'moving fast', 'eng');
        INSERT INTO synset_def VALUES (2, '02119022-n', 'a wild canine', 'eng');
        INSERT INTO synset_def VALUES (3, '01965856-v', 'to leap', 'eng');
        INSERT INTO synset_def VALUES (4, '03326073-n', 'a barrier', 'eng');
        INSERT INTO synset_def VALUES (5, '01068018-a', '速い', 'jpn');
        INSERT INTO synset_def VALUES (6, '02119022-n', '野生の犬科', 'jpn');

        CREATE TABLE sense (sid INTEGER PRIMARY KEY, synset TEXT,
                            wordid INTEGER, lang TEXT,
                            confidence REAL, freq INTEGER);
        CREATE TABLE word (wordid INTEGER PRIMARY KEY, lemma TEXT, pos TEXT,
                           lang TEXT);

        INSERT INTO word VALUES (1, 'quick', 'a', 'eng');
        INSERT INTO word VALUES (2, 'fast', 'a', 'eng');
        INSERT INTO word VALUES (3, 'fox', 'n', 'eng');
        INSERT INTO word VALUES (4, 'jump', 'v', 'eng');
        INSERT INTO word VALUES (5, 'fence', 'n', 'eng');
        INSERT INTO word VALUES (6, '速い', 'a', 'jpn');
        INSERT INTO word VALUES (7, 'キツネ', 'n', 'jpn');

        INSERT INTO sense VALUES (1, '01068018-a', 1, 'eng', 1.0, 10);
        INSERT INTO sense VALUES (2, '01068018-a', 2, 'eng', 0.9, 5);
        INSERT INTO sense VALUES (3, '02119022-n', 3, 'eng', 1.0, 8);
        INSERT INTO sense VALUES (4, '01965856-v', 4, 'eng', 1.0, 6);
        INSERT INTO sense VALUES (5, '03326073-n', 5, 'eng', 1.0, 4);
        INSERT INTO sense VALUES (6, '01068018-a', 6, 'jpn', 1.0, 3);
        INSERT INTO sense VALUES (7, '02119022-n', 7, 'jpn', 1.0, 2);
    """)
    conn.close()
    return db_path


@pytest.fixture()
def link_dbs(tmp_path):
    """Create link databases for testing build_data_files.

    Sets up tmp_path as a mock BUILD_DIR with corpus DBs and link DBs.
    """
    # eng.db
    eng_db = tmp_path / "eng.db"
    conn = sqlite3.connect(str(eng_db))
    conn.executescript("""
        CREATE TABLE sent (sid INTEGER PRIMARY KEY, docID INTEGER,
                           sent TEXT, comment TEXT);
        INSERT INTO sent VALUES (1, 1, 'Hello world', NULL);
        INSERT INTO sent VALUES (2, 1, 'Good morning', NULL);
        INSERT INTO sent VALUES (3, 1, 'Good night', NULL);

        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, comment TEXT);
        INSERT INTO concept VALUES (1, 1, 'hello', '12345-n', NULL);
    """)
    conn.close()

    # jpn.db
    jpn_db = tmp_path / "jpn.db"
    conn = sqlite3.connect(str(jpn_db))
    conn.executescript("""
        CREATE TABLE sent (sid INTEGER PRIMARY KEY, docID INTEGER,
                           sent TEXT, comment TEXT);
        INSERT INTO sent VALUES (1, 1, 'こんにちは世界', NULL);
        INSERT INTO sent VALUES (2, 1, 'おはようございます', NULL);

        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, comment TEXT);
    """)
    conn.close()

    # cmn.db
    cmn_db = tmp_path / "cmn.db"
    conn = sqlite3.connect(str(cmn_db))
    conn.executescript("""
        CREATE TABLE sent (sid INTEGER PRIMARY KEY, docID INTEGER,
                           sent TEXT, comment TEXT);
        INSERT INTO sent VALUES (1, 1, '你好世界', NULL);
        INSERT INTO sent VALUES (2, 1, '早上好', NULL);
        INSERT INTO sent VALUES (3, 1, '晚安', NULL);

        CREATE TABLE concept (sid INTEGER, cid INTEGER, clemma TEXT,
                              tag TEXT, comment TEXT);
    """)
    conn.close()

    # eng-jpn.db
    eng_jpn = tmp_path / "eng-jpn.db"
    conn = sqlite3.connect(str(eng_jpn))
    conn.executescript("""
        CREATE TABLE slink (slid INTEGER PRIMARY KEY,
                            fsid INTEGER NOT NULL, tsid INTEGER NOT NULL,
                            ltype TEXT, conf FLOAT, comment TEXT, usrname TEXT,
                            UNIQUE(fsid, tsid));
        INSERT INTO slink VALUES (1, 1, 1, NULL, 1.0, NULL, NULL);
        INSERT INTO slink VALUES (2, 2, 2, NULL, 1.0, NULL, NULL);
    """)
    conn.close()

    # eng-cmn.db
    eng_cmn = tmp_path / "eng-cmn.db"
    conn = sqlite3.connect(str(eng_cmn))
    conn.executescript("""
        CREATE TABLE slink (slid INTEGER PRIMARY KEY,
                            fsid INTEGER NOT NULL, tsid INTEGER NOT NULL,
                            ltype TEXT, conf FLOAT, comment TEXT, usrname TEXT,
                            UNIQUE(fsid, tsid));
        INSERT INTO slink VALUES (1, 1, 1, NULL, 1.0, NULL, NULL);
        INSERT INTO slink VALUES (2, 2, 2, NULL, 1.0, NULL, NULL);
        INSERT INTO slink VALUES (3, 3, 3, NULL, 1.0, NULL, NULL);
    """)
    conn.close()

    # Minimal wn-ntumc.db
    wn = tmp_path / "wn-ntumc.db"
    conn = sqlite3.connect(str(wn))
    conn.executescript("""
        CREATE TABLE synset (synset TEXT PRIMARY KEY, pos TEXT);
        INSERT INTO synset VALUES ('12345-n', 'n');

        CREATE TABLE synset_def (sid INTEGER PRIMARY KEY, synset TEXT,
                                 def TEXT, lang TEXT);
        INSERT INTO synset_def VALUES (1, '12345-n', 'a greeting', 'eng');

        CREATE TABLE sense (sid INTEGER PRIMARY KEY, synset TEXT,
                            wordid INTEGER, lang TEXT,
                            confidence REAL, freq INTEGER);
        CREATE TABLE word (wordid INTEGER PRIMARY KEY, lemma TEXT,
                           pos TEXT, lang TEXT);
        INSERT INTO word VALUES (1, 'hello', 'n', 'eng');
        INSERT INTO sense VALUES (1, '12345-n', 1, 'eng', 1.0, 10);
    """)
    conn.close()

    return tmp_path


# ---------------------------------------------------------------------------
# compute_nospace
# ---------------------------------------------------------------------------


class TestComputeNospace:
    """Tests for compute_nospace spacing logic."""

    def test_empty_words(self):
        assert compute_nospace([], "") == []

    def test_single_word(self):
        words = [{"word": "Hello"}]
        assert compute_nospace(words, "Hello") == [False]

    def test_cfrom_cto_spaced(self):
        words = [
            {"word": "The", "cfrom": 0, "cto": 3},
            {"word": "fox", "cfrom": 4, "cto": 7},
        ]
        result = compute_nospace(words, "The fox")
        assert result == [False, False]

    def test_cfrom_cto_nospace(self):
        words = [
            {"word": "don", "cfrom": 0, "cto": 3},
            {"word": "'t", "cfrom": 3, "cto": 5},
        ]
        result = compute_nospace(words, "don't")
        assert result == [True, False]

    def test_fallback_scanning(self):
        words = [
            {"word": "don"},
            {"word": "'t"},
        ]
        result = compute_nospace(words, "don't")
        assert result == [True, False]

    def test_fallback_with_space(self):
        words = [{"word": "a"}, {"word": "b"}]
        result = compute_nospace(words, "a b")
        assert result == [False, False]

    def test_japanese_no_spaces(self):
        words = [
            {"word": "東京", "cfrom": 0, "cto": 2},
            {"word": "は", "cfrom": 2, "cto": 3},
            {"word": "大きい", "cfrom": 3, "cto": 6},
        ]
        result = compute_nospace(words, "東京は大きい")
        assert result == [True, True, False]


# ---------------------------------------------------------------------------
# build_concept_info
# ---------------------------------------------------------------------------


class TestBuildConceptInfo:
    """Tests for concept extraction and word annotation."""

    def _make_doc(self, concepts, words=None):
        """Create a minimal doc_data dict."""
        if words is None:
            words = [
                {"word": "The", "wid": 0},
                {"word": "fox", "wid": 1},
            ]
        return {
            "sentences": [{
                "sid": 1,
                "text": "The fox",
                "words": words,
                "concepts": concepts,
            }],
        }

    def test_basic_concept_extraction(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "fox", "tag": "02119022-n", "wids": [1]},
        ])
        concepts, stats, _ = build_concept_info(doc)
        assert "c1:1" in concepts
        assert concepts["c1:1"]["l"] == "fox"
        assert concepts["c1:1"]["s"] == "02119022-n"
        assert concepts["c1:1"]["w"] == [1]
        assert stats["tagged"] == 1

    def test_skip_tags_excluded(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "the", "tag": "x", "wids": [0]},
            {"cid": 2, "clemma": "the", "tag": "w", "wids": [0]},
            {"cid": 3, "clemma": "the", "tag": "e", "wids": [0]},
            {"cid": 4, "clemma": "fox", "tag": "02119022-n", "wids": [1]},
        ])
        concepts, stats, _ = build_concept_info(doc)
        assert len(concepts) == 1
        assert "c1:4" in concepts
        assert stats["x"] == 1
        assert stats["w"] == 1
        assert stats["e"] == 1
        assert stats["tagged"] == 1

    def test_empty_tag_excluded(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "the", "tag": "", "wids": [0]},
            {"cid": 2, "clemma": "the", "tag": None, "wids": [0]},
        ])
        concepts, stats, _ = build_concept_info(doc)
        assert len(concepts) == 0
        assert stats["null"] == 2

    def test_word_cids_annotation(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "fox", "tag": "02119022-n", "wids": [1]},
        ])
        build_concept_info(doc)  # returns (concepts, stats, has_sentiment); we check mutation
        word_cids = doc["sentences"][0]["word_cids"]
        assert 1 in word_cids
        assert word_cids[1] == ["c1:1"]
        assert 0 not in word_cids

    def test_multiword_expression(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "the fox", "tag": "02119022-n", "wids": [0, 1]},
        ])
        concepts, _, __ = build_concept_info(doc)
        assert concepts["c1:1"]["w"] == [0, 1]
        word_cids = doc["sentences"][0]["word_cids"]
        assert word_cids[0] == ["c1:1"]
        assert word_cids[1] == ["c1:1"]

    def test_nospace_annotation(self):
        words = [
            {"word": "don", "wid": 0, "cfrom": 0, "cto": 3},
            {"word": "'t", "wid": 1, "cfrom": 3, "cto": 5},
        ]
        doc = self._make_doc([], words=words)
        build_concept_info(doc)  # returns (concepts, stats, has_sentiment); we check mutation
        assert doc["sentences"][0]["words"][0]["nospace"] is True
        assert doc["sentences"][0]["words"][1]["nospace"] is False

    def test_named_entity_included(self):
        doc = self._make_doc([
            {"cid": 1, "clemma": "Tokyo", "tag": "org", "wids": [0]},
        ])
        concepts, _, __ = build_concept_info(doc)
        assert concepts["c1:1"]["s"] == "org"


# ---------------------------------------------------------------------------
# cross_compile_slinks
# ---------------------------------------------------------------------------


class TestCrossCompileSlinks:
    """Tests for transitive slink computation."""

    def test_no_cross_needed(self):
        direct = {
            ("eng", "jpn"): {1: [1], 2: [2]},
            ("jpn", "eng"): {1: [1], 2: [2]},
        }
        result = cross_compile_slinks(direct)
        assert len(result) == 2

    def test_basic_cross_compilation(self):
        direct = {
            ("eng", "jpn"): {10: [20]},
            ("jpn", "eng"): {20: [10]},
            ("eng", "cmn"): {10: [30]},
            ("cmn", "eng"): {30: [10]},
        }
        result = cross_compile_slinks(direct)
        assert ("jpn", "cmn") in result
        assert ("cmn", "jpn") in result
        assert result[("jpn", "cmn")] == {20: [30]}
        assert result[("cmn", "jpn")] == {30: [20]}

    def test_one_to_many_cross(self):
        direct = {
            ("eng", "jpn"): {1: [10, 11]},
            ("jpn", "eng"): {10: [1], 11: [1]},
            ("eng", "cmn"): {1: [20]},
            ("cmn", "eng"): {20: [1]},
        }
        result = cross_compile_slinks(direct)
        assert sorted(result[("jpn", "cmn")][10]) == [20]
        assert sorted(result[("jpn", "cmn")][11]) == [20]
        assert sorted(result[("cmn", "jpn")][20]) == [10, 11]

    def test_no_common_pivot(self):
        direct = {
            ("eng", "jpn"): {1: [10]},
            ("jpn", "eng"): {10: [1]},
            ("fra", "deu"): {100: [200]},
            ("deu", "fra"): {200: [100]},
        }
        result = cross_compile_slinks(direct)
        assert ("jpn", "fra") not in result
        assert ("eng", "deu") not in result

    def test_direct_not_overwritten(self):
        direct = {
            ("eng", "jpn"): {1: [10]},
            ("jpn", "eng"): {10: [1]},
            ("eng", "cmn"): {1: [20]},
            ("cmn", "eng"): {20: [1]},
            ("jpn", "cmn"): {10: [99]},
            ("cmn", "jpn"): {99: [10]},
        }
        result = cross_compile_slinks(direct)
        assert result[("jpn", "cmn")] == {10: [99]}


# ---------------------------------------------------------------------------
# render_html
# ---------------------------------------------------------------------------


class TestRenderHtml:
    """Tests for HTML template rendering."""

    def test_basic_render(self):
        doc_data = {
            "title": "Test",
            "subtitle": "Sub",
            "sentences": [],
        }
        html = render_html(doc_data, {}, "eng", "../assets", "../index.html")
        assert "<!DOCTYPE html>" in html
        assert "<title>Test</title>" in html
        assert 'var docLang = "eng"' in html
        assert 'var dataPath = "../data"' in html

    def test_concept_data_embedded(self):
        doc_data = {"title": "T", "subtitle": "", "sentences": []}
        concepts = {"c1:1": {"l": "fox", "s": "02119022-n", "w": [1]}}
        html = render_html(doc_data, concepts, "eng", "../assets", "../index.html")
        assert "02119022-n" in html
        assert "conceptInfo" in html

    def test_no_synset_info_in_page(self):
        doc_data = {"title": "T", "subtitle": "", "sentences": []}
        html = render_html(doc_data, {}, "eng", "../assets", "../index.html")
        assert "synsetInfo" not in html

    def test_translate_icons_present(self):
        doc_data = {
            "title": "T", "subtitle": "",
            "sentences": [{
                "sid": 100,
                "stype": "p",
                "words": [{"word": "Hi", "wid": 0, "pos": "UH", "lemma": "hi"}],
                "word_cids": {},
            }],
        }
        html = render_html(doc_data, {}, "eng", "../assets", "../index.html")
        assert 'data-sid="100"' in html
        assert "trans-icon" in html

    def test_language_dropdowns_in_settings(self):
        doc_data = {"title": "T", "subtitle": "", "sentences": []}
        html = render_html(doc_data, {}, "eng", "../assets", "../index.html")
        assert "defLangSelect" in html
        assert "synLangSelect" in html
        assert "transLangSelect" in html
        assert "Definition language" in html
        assert "Synonym language" in html
        assert "Sentence translation" in html


# ---------------------------------------------------------------------------
# build_data_files (integration)
# ---------------------------------------------------------------------------


class TestBuildDataFiles:
    """Integration tests for shared JSON data file generation."""

    def test_creates_all_files(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        data_dir = tmp_outdir / "data"
        assert (data_dir / "manifest.json").exists()
        assert (data_dir / "slinks.json").exists()
        assert (data_dir / "sent-eng.json").exists()
        assert (data_dir / "sent-jpn.json").exists()
        assert (data_dir / "sent-cmn.json").exists()

    def test_slinks_structure(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        slinks = json.loads(
            (tmp_outdir / "data" / "slinks.json").read_text(encoding="utf-8")
        )
        assert "eng" in slinks
        assert "jpn" in slinks["eng"]
        assert "cmn" in slinks["eng"]
        assert slinks["eng"]["jpn"]["1"] == [1]
        assert slinks["eng"]["jpn"]["2"] == [2]

    def test_cross_compiled_links_in_slinks(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        slinks = json.loads(
            (tmp_outdir / "data" / "slinks.json").read_text(encoding="utf-8")
        )
        assert "jpn" in slinks
        assert "cmn" in slinks["jpn"]
        assert slinks["jpn"]["cmn"]["1"] == [1]
        assert slinks["jpn"]["cmn"]["2"] == [2]

    def test_sentence_files_content(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        sent_jpn = json.loads(
            (tmp_outdir / "data" / "sent-jpn.json").read_text(encoding="utf-8")
        )
        assert sent_jpn["1"] == "こんにちは世界"
        assert sent_jpn["2"] == "おはようございます"

        sent_eng = json.loads(
            (tmp_outdir / "data" / "sent-eng.json").read_text(encoding="utf-8")
        )
        assert sent_eng["1"] == "Hello world"

    def test_manifest_structure(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        manifest = json.loads(
            (tmp_outdir / "data" / "manifest.json").read_text(encoding="utf-8")
        )
        assert "lang_names" in manifest
        assert "ne_defs" in manifest
        assert "defs" in manifest
        assert "syns" in manifest
        assert "trans" in manifest
        assert "eng" in manifest["lang_names"]
        assert "per" in manifest["ne_defs"]
        assert "eng" in manifest["trans"]
        assert "jpn" in manifest["trans"]["eng"]

    def test_wn_defs_extracted(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        defs_path = tmp_outdir / "data" / "wn-defs-eng.json"
        assert defs_path.exists()
        defs = json.loads(defs_path.read_text(encoding="utf-8"))
        assert defs["12345-n"] == "a greeting"

    def test_wn_syns_extracted(self, link_dbs, tmp_outdir):
        import scripts.make_display as md
        original_build = md.BUILD_DIR
        md.BUILD_DIR = link_dbs
        try:
            build_data_files(tmp_outdir, str(link_dbs / "wn-ntumc.db"))
        finally:
            md.BUILD_DIR = original_build

        syns_path = tmp_outdir / "data" / "wn-syns-eng.json"
        assert syns_path.exists()
        syns = json.loads(syns_path.read_text(encoding="utf-8"))
        assert "12345-n" in syns
        assert "hello" in syns["12345-n"]


# ---------------------------------------------------------------------------
# write_document (integration)
# ---------------------------------------------------------------------------


class TestWriteDocument:
    """Integration tests for single document HTML generation."""

    def test_produces_html(self, corpus_db, tmp_outdir):
        meta = write_document(str(corpus_db), 1, tmp_outdir, "eng")
        assert meta is not None
        assert meta["title"] == "Test Document"
        assert meta["sent_count"] == 2

        html_path = tmp_outdir / "eng" / "testdoc-view.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Test Document" in html
        assert 'var docLang = "eng"' in html

    def test_concepts_in_html(self, corpus_db, tmp_outdir):
        write_document(str(corpus_db), 1, tmp_outdir, "eng")
        html_path = tmp_outdir / "eng" / "testdoc-view.html"
        html = html_path.read_text(encoding="utf-8")
        assert "01068018-a" in html
        assert "02119022-n" in html
        # Skip-tagged concept should not appear
        assert "conceptInfo" in html

    def test_nonexistent_doc_returns_none(self, corpus_db, tmp_outdir):
        meta = write_document(str(corpus_db), 999, tmp_outdir, "eng")
        assert meta is None

    def test_tag_rate_in_metadata(self, corpus_db, tmp_outdir):
        meta = write_document(str(corpus_db), 1, tmp_outdir, "eng", tag_rate=0.75)
        assert meta["tag_pct"] == "75"

    def test_words_in_html(self, corpus_db, tmp_outdir):
        write_document(str(corpus_db), 1, tmp_outdir, "eng")
        html_path = tmp_outdir / "eng" / "testdoc-view.html"
        html = html_path.read_text(encoding="utf-8")
        assert ">The<" in html
        assert ">quick<" in html
        assert ">fox<" in html
        assert 'data-p="JJ"' in html
        assert 'data-l="quick"' in html

    def test_produces_json(self, corpus_db, tmp_outdir):
        write_document(str(corpus_db), 1, tmp_outdir, "eng")
        json_path = tmp_outdir / "data" / "docs" / "eng-fiction-testdoc.jsonl"
        assert json_path.exists()

    def test_genre_in_html(self, corpus_db, tmp_outdir):
        write_document(str(corpus_db), 1, tmp_outdir, "eng")
        html = (tmp_outdir / "eng" / "testdoc-view.html").read_text(encoding="utf-8")
        assert 'var docGenre = "fiction"' in html

    def test_unknown_corpus_code_raises(self, tmp_path, tmp_outdir):
        db_path = tmp_path / "bad.db"
        conn = sqlite3.connect(str(db_path))
        _create_corpus_schema(conn, with_genre=False)
        conn.execute("INSERT INTO corpus VALUES (1, 'Test', 'bogus')")
        conn.execute("INSERT INTO doc VALUES (1, 'testdoc', 'Test', '', 1)")
        conn.commit()
        conn.close()
        with pytest.raises(ValueError, match="migrate_genre"):
            write_document(str(db_path), 1, tmp_outdir, "eng")


# ---------------------------------------------------------------------------
# write_doc_json
# ---------------------------------------------------------------------------


class TestWriteDocJson:
    """Tests for per-document NDJSON annotation output."""

    def _make_doc(self):
        return {
            "docid": 1,
            "doc": "testdoc",
            "title": "Test Document",
            "subtitle": "A test",
            "sentences": [
                {
                    "sid": 100,
                    "text": "The fox.",
                    "stype": "p",
                    "words": [
                        {"wid": 0, "word": "The", "pos": "DT", "lemma": "the",
                         "nospace": False},
                        {"wid": 1, "word": "fox", "pos": "NN", "lemma": "fox",
                         "nospace": False},
                    ],
                    "concepts": [
                        {"cid": 1, "tag": "02119022-n", "clemma": "fox", "wids": [1]},
                        {"cid": 2, "tag": "x", "clemma": "the", "wids": [0]},
                    ],
                    "word_cids": {1: ["c100:1"]},
                }
            ],
        }

    def test_filename_encodes_lang_genre_doc(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        assert path.name == "eng-fiction-testdoc.jsonl"

    def test_valid_ndjson(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["docid"] == 1
        assert record["lang"] == "eng"
        assert record["genre"] == "fiction"

    def test_no_nospace_in_output(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        record = json.loads(path.read_text(encoding="utf-8").strip())
        for word in record["sentences"][0]["words"]:
            assert "nospace" not in word

    def test_no_word_cids_in_output(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert "word_cids" not in record["sentences"][0]

    def test_all_concepts_preserved(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        record = json.loads(path.read_text(encoding="utf-8").strip())
        concepts = record["sentences"][0]["concepts"]
        assert len(concepts) == 2
        tags = {c["tag"] for c in concepts}
        assert tags == {"02119022-n", "x"}

    def test_stype_included_when_present(self, tmp_outdir):
        path = write_doc_json(self._make_doc(), "eng", "fiction", tmp_outdir)
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert record["sentences"][0]["stype"] == "p"

    def test_subtitle_omitted_when_empty(self, tmp_outdir):
        doc = self._make_doc()
        doc["subtitle"] = ""
        path = write_doc_json(doc, "eng", "fiction", tmp_outdir)
        record = json.loads(path.read_text(encoding="utf-8").strip())
        assert "subtitle" not in record


# ---------------------------------------------------------------------------
# write_consolidated_json
# ---------------------------------------------------------------------------


class TestWriteConsolidatedJson:
    """Tests for consolidated NDJSON rollup files."""

    def _seed_docs(self, outdir, docs):
        docs_dir = outdir / "data" / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        for fname, record in docs:
            (docs_dir / fname).write_text(
                json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )

    def test_creates_all_rollup_files(self, tmp_outdir):
        self._seed_docs(tmp_outdir, [
            ("eng-fiction-s1.jsonl",
             {"lang": "eng", "genre": "fiction", "title": "T", "sentences": []}),
            ("jpn-fiction-s1.jsonl",
             {"lang": "jpn", "genre": "fiction", "title": "T", "sentences": []}),
            ("eng-news-k1.jsonl",
             {"lang": "eng", "genre": "news", "title": "T", "sentences": []}),
        ])
        write_consolidated_json(tmp_outdir)
        data = tmp_outdir / "data"
        assert (data / "lang" / "eng.jsonl").exists()
        assert (data / "lang" / "jpn.jsonl").exists()
        assert (data / "genre" / "fiction.jsonl").exists()
        assert (data / "genre" / "news.jsonl").exists()
        assert (data / "corpus.jsonl").exists()

    def test_lang_file_line_counts(self, tmp_outdir):
        self._seed_docs(tmp_outdir, [
            ("eng-fiction-s1.jsonl",
             {"lang": "eng", "genre": "fiction", "title": "T", "sentences": []}),
            ("eng-news-k1.jsonl",
             {"lang": "eng", "genre": "news", "title": "T", "sentences": []}),
            ("jpn-fiction-s1.jsonl",
             {"lang": "jpn", "genre": "fiction", "title": "T", "sentences": []}),
        ])
        write_consolidated_json(tmp_outdir)
        eng = (tmp_outdir / "data" / "lang" / "eng.jsonl").read_text().strip().splitlines()
        jpn = (tmp_outdir / "data" / "lang" / "jpn.jsonl").read_text().strip().splitlines()
        assert len(eng) == 2
        assert len(jpn) == 1

    def test_corpus_has_all_docs(self, tmp_outdir):
        self._seed_docs(tmp_outdir, [
            ("eng-fiction-s1.jsonl",
             {"lang": "eng", "genre": "fiction", "title": "T", "sentences": []}),
            ("jpn-news-k1.jsonl",
             {"lang": "jpn", "genre": "news", "title": "T", "sentences": []}),
        ])
        write_consolidated_json(tmp_outdir)
        lines = (tmp_outdir / "data" / "corpus.jsonl").read_text().strip().splitlines()
        assert len(lines) == 2

    def test_missing_docs_dir_warns(self, tmp_outdir, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            write_consolidated_json(tmp_outdir)
        assert "No docs/ directory found" in caplog.text
