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


def test_ili_map_matches_satellites_as_adjectives(tmp_path) -> None:
    """A satellite in the ILI map (-s) is also found under -a."""
    from getwn import load_ili_map

    tab = tmp_path / "ili-map-pwn30.tab"
    tab.write_text("i10\t00003553-s\ni1\t00001740-a\n", encoding="utf-8")

    ili = load_ili_map(str(tab))

    assert ili["00003553-a"] == "i10"
    assert ili["00001740-a"] == "i1"
