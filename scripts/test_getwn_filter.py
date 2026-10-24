"""Tests for the sense-source filter in getwn.py (curated COW export)."""

from getwn import filter_senses, source_tags

EXCLUDE = {"bow", "sew", "wikt", "cmn:mwe"}


def row(src: str) -> tuple:
    """A sense row with the given src field."""
    return ("00001740-n", 1, 0, 1.0, src)


def test_source_tags_keeps_cmn_mwe_whole() -> None:
    """cmn:mwe is one tag; other tags split on ';' and ':'."""
    assert source_tags("bow;cmn:mwe") == {"bow", "cmn:mwe"}
    assert source_tags("pron:wikt") == {"pron", "wikt"}
    assert source_tags(None) == set()


def test_drops_senses_only_from_excluded_sources() -> None:
    """bow/sew/wikt-only senses go; a curated tag or no source keeps one."""
    rows = [row("bow"), row("bow;sew"), row("bow;cow"), row("ntumc"), row("")]

    kept = [r[4] for r in filter_senses(rows, EXCLUDE)]

    assert kept == ["bow;cow", "ntumc", ""]


def test_drops_every_segmented_sense() -> None:
    """A cmn:mwe sense is dropped even when it has a curated tag."""
    rows = [row("cmn:mwe"), row("cmn:mwe;ntumc"), row("cow")]

    kept = [r[4] for r in filter_senses(rows, EXCLUDE)]

    assert kept == ["cow"]


def test_load_examples_by_language_in_sid_order() -> None:
    """Examples come back per synset, sid-ordered, for one language only."""
    import sqlite3

    from getwn import load_examples

    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE synset_ex (synset, lang, def, sid, usr)")
    con.executemany(
        "INSERT INTO synset_ex VALUES (?, ?, ?, ?, '')",
        [("00001740-n", "jpn", "二番目", 1), ("00001740-n", "jpn", "一番目", 0),
         ("00001740-n", "eng", "first", 0), ("00002137-n", "jpn", " ", 0)],
    )

    exes = load_examples(con.cursor(), "jpn")

    assert exes == {"00001740-n": ["一番目", "二番目"]}


def test_split_gaps_drops_nolex_senses() -> None:
    """NOLEX and META:NOLEX mark lexical gaps; they are not lemmas."""
    from getwn import split_gaps

    words = {1: ("NOLEX", "v"), 2: ("META:NOLEX", "a"), 3: ("運ぶ", "v")}
    rows = [("01451502-v", 1, 0, 1.0, ""), ("80001278-a", 2, 0, 1.0, ""),
            ("01449974-v", 3, 0, 1.0, "")]

    kept, gaps = split_gaps(rows, words)

    assert [r[1] for r in kept] == [3]
    assert gaps == {"01451502-v", "80001278-a"}


def test_ili_map_matches_satellites_as_adjectives(tmp_path) -> None:
    """A satellite in the ILI map (-s) is also found under -a."""
    from getwn import load_ili_map

    tab = tmp_path / "ili-map-pwn30.tab"
    tab.write_text("i10\t00003553-s\ni1\t00001740-a\n", encoding="utf-8")

    ili = load_ili_map(str(tab))

    assert ili["00003553-a"] == "i10"
    assert ili["00001740-a"] == "i1"
