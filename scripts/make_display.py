#!/usr/bin/env python3
"""Generate static HTML corpus display pages for NTUMC documents.

Each document produces one self-contained HTML file in OUTDIR/{lang}/.
Concept-to-synset mappings are embedded inline; synset definitions, synonyms,
and sentence translations are loaded dynamically from shared JSON data files.

Usage:
    .venv/bin/python scripts/make_display.py --lang eng --doc spec --outdir display/
    .venv/bin/python scripts/make_display.py --lang eng --all --tagged --outdir display/
    .venv/bin/python scripts/make_display.py --build-data --outdir display/
"""

import argparse
import json
import logging
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ntumc.corpus import Document, Word, db, jsonl  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

LANG_NAMES: dict[str, str] = {
    "eng": "English",
    "cmn": "Chinese",
    "jpn": "Japanese",
    "ind": "Indonesian",
    "ita": "Italian",
    "ces": "Czech",
    "kor": "Korean",
    "vie": "Vietnamese",
    "tha": "Thai",
}

NAMED_ENTITY_DEFS: dict[str, str] = {
    "per": "Person Name",
    "num": "Number",
    "dat": "Date",
    "org": "Organisation Name",
    "oth": "Other Name",
}
SKIP_TAGS: frozenset[str] = frozenset({"x", "w", "e"})

GENRE_NAMES: dict[str, str] = {
    "news":    "News",
    "fiction": "Fiction",
    "tourism": "Tourism",
    "essay":   "Essay",
    "online":  "Online",
    "lexical": "Lexical",
}
GENRE_ORDER: list[str] = ["news", "fiction", "tourism", "essay", "online", "lexical"]

# ---------------------------------------------------------------------------
# Templates — loaded from scripts/templates/ for easy editing
# ---------------------------------------------------------------------------


_jinja_env: Optional[Environment] = None


def _get_env() -> Environment:
    """Return a shared Jinja2 environment loading from the templates directory."""
    global _jinja_env
    if _jinja_env is None:
        _jinja_env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=True,
        )
        _jinja_env.filters["commaformat"] = lambda v: f"{v:,}"
    return _jinja_env

# ---------------------------------------------------------------------------
# Spacing calculation
# ---------------------------------------------------------------------------


def compute_nospace(words: list[Word], sent_text: str) -> list[bool]:
    """Compute nospace flag for each word (True = no space before next word).

    Uses cfrom/cto offsets when present; falls back to scanning sent_text.
    The last word always returns False.

    Args:
        words: The words of the sentence in order.
        sent_text: The full sentence text.

    Returns:
        List of bool, same length as words.
    """
    n = len(words)
    if n == 0:
        return []

    # Try cfrom/cto first
    if n > 1 and words[0].cfrom is not None and words[1].cfrom is not None:
        result = []
        for i, w in enumerate(words):
            if i < n - 1 and w.cto is not None and words[i + 1].cfrom is not None:
                result.append(w.cto == words[i + 1].cfrom)
            else:
                result.append(False)
        return result

    # Fall back: scan sentence text
    result = [False] * n
    pos = 0
    for i, w in enumerate(words[:-1]):
        idx = sent_text.find(w.word, pos)
        if idx == -1:
            continue
        pos = idx + len(w.word)
        if sent_text.find(words[i + 1].word, pos) == pos:
            result[i] = True

    return result


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def build_concept_info(doc: Document) -> tuple[dict, dict, bool]:
    """Extract the concepts to embed in the page and count the annotation.

    Args:
        doc: The document.

    Returns:
        (concepts, doc_stats, has_sentiment) where concepts is
        {concept_key: {l, s, w[, v]}} and doc_stats is
        {sents, words, tagged, w, e, x, null}.
    """
    concepts: dict = {}
    stats = {"words": 0, "tagged": 0, "w": 0, "e": 0, "x": 0, "null": 0}
    has_sentiment = False

    for sent in doc.sentences:
        stats["words"] += len(sent.words)
        for concept in sent.concepts:
            tag = concept.tag or ""
            if tag in ("x", "w", "e"):
                stats[tag] += 1
                continue
            if not tag:
                stats["null"] += 1
                continue
            stats["tagged"] += 1
            entry: dict = {"l": concept.clemma, "s": tag, "w": concept.wids}
            if concept.sentiment is not None:
                entry["v"] = concept.sentiment
                has_sentiment = True
            concepts[f"c{sent.sid}:{concept.cid}"] = entry

    doc_stats = {"sents": len(doc.sentences), **stats}
    return concepts, doc_stats, has_sentiment


def sentence_views(doc: Document, concepts: dict) -> list[dict]:
    """Prepare the sentences for the document template.

    Args:
        doc: The document.
        concepts: The embedded concepts from ``build_concept_info``; a
            word carries the keys of the concepts covering it.

    Returns:
        One dict per sentence: sid, stype and words, each word a dict
        with wid, word, pos, lemma, nospace and cids.
    """
    views = []
    for sent in doc.sentences:
        word_cids: dict[int, list[str]] = {}
        for concept in sent.concepts:
            key = f"c{sent.sid}:{concept.cid}"
            if key in concepts:
                for wid in concept.wids:
                    word_cids.setdefault(wid, []).append(key)
        nospace = compute_nospace(sent.words, sent.text)
        views.append(
            {
                "sid": sent.sid,
                "stype": sent.stype,
                "words": [
                    {
                        "wid": w.wid,
                        "word": w.word,
                        "pos": w.pos or "",
                        "lemma": w.lemma or "",
                        "nospace": ns,
                        "cids": word_cids.get(w.wid, []),
                    }
                    for w, ns in zip(sent.words, nospace)
                ],
            }
        )
    return views


def get_doc_tagging_rates(corpus_db: str) -> dict[int, float]:
    """Return concept-level tagging rates (0–1) for every document.

    Rate = |tagged concepts| / |taggable concepts|, where:
      - tagged: concept has a real sense tag (not NULL, '', 'e', 'w', or 'x')
      - taggable: all concepts except those tagged 'x' (shouldn't be tagged)

    Args:
        corpus_db: Path to the corpus database.

    Returns:
        {docid: rate}
    """
    conn = sqlite3.connect(corpus_db)
    try:
        rows = conn.execute(
            """
            SELECT
                s.docID,
                -- taggable: all concepts except 'x'
                COUNT(DISTINCT CASE
                    WHEN c.tag IS NULL OR c.tag != 'x'
                    THEN c.sid || ':' || CAST(c.cid AS TEXT)
                END) AS taggable,
                -- tagged: has a real sense tag
                COUNT(DISTINCT CASE
                    WHEN c.tag IS NOT NULL AND c.tag != ''
                         AND c.tag NOT IN ('x', 'w', 'e')
                    THEN c.sid || ':' || CAST(c.cid AS TEXT)
                END) AS tagged
            FROM sent s
            JOIN concept c ON c.sid = s.sid
            GROUP BY s.docID
            """
        ).fetchall()
        return {
            docid: (tagged / taggable if taggable > 0 else 0.0)
            for docid, taggable, tagged in rows
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


@dataclass
class PageData:
    """What the document template needs."""

    title: str
    lang: str
    subtitle: str = ""
    sentences: list[dict] = field(default_factory=list)
    concepts: dict = field(default_factory=dict)
    doc_stats: dict = field(default_factory=dict)
    genre: str = "other"
    has_sentiment: bool = False


def render_html(page: PageData, assets_path: str, index_path: str) -> str:
    """Render the document HTML page with concept data embedded inline.

    Synset definitions, synonyms, and translations are loaded dynamically
    from shared JSON data files.

    Args:
        page: Title, sentences (from ``sentence_views``), concepts and stats.
        assets_path: Relative path from HTML file to the assets/ directory.
        index_path: Relative path to the index HTML file.

    Returns:
        Rendered HTML string.
    """
    tmpl = _get_env().get_template("document.html")
    return tmpl.render(
        title=page.title,
        subtitle=page.subtitle,
        sentences=page.sentences,
        assets_path=assets_path,
        index_path=index_path,
        concepts_data=Markup(json.dumps(page.concepts, ensure_ascii=False)),
        doc_lang_json=Markup(json.dumps(page.lang)),
        doc_genre_json=Markup(json.dumps(page.genre)),
        doc_has_sentiment_json=Markup(json.dumps(page.has_sentiment)),
        data_path_json=Markup(json.dumps("../data")),
        doc_stats_json=Markup(json.dumps(page.doc_stats)),
    )


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def write_document(
    corpus_db: str,
    docid: int,
    outdir: Path,
    lang: str,
    tag_rate: Optional[float] = None,
) -> Optional[dict]:
    """Generate the HTML display file and the JSON record for one document.

    Args:
        corpus_db: Path to the language corpus database.
        docid: Document ID to process.
        outdir: Root output directory (e.g. display/).
        lang: Language code (e.g. 'eng').
        tag_rate: Pre-computed tagging rate (0-1), used for index display.

    Returns:
        Dict with doc metadata for index generation, or None if the
        document does not exist.

    Raises:
        ValueError: If the document's collection has no genre.
    """
    conn = db.connect(corpus_db)
    try:
        doc = db.read_document(conn, lang, docid)
    except KeyError:
        logger.error("Document %d not found in %s", docid, corpus_db)
        return None
    finally:
        conn.close()
    if doc.genre is None:
        raise ValueError(
            f"No genre for document {docid} in {corpus_db} "
            f"— run scripts/migrate_genre.py first"
        )

    title = doc.title or doc.doc
    tag_pct = f"{tag_rate * 100:.0f}" if tag_rate is not None else ""
    logger.info(
        "Processing '%s' (%d sentences%s)...",
        title,
        len(doc),
        f", {tag_pct}% tagged" if tag_pct else "",
    )

    concepts, doc_stats, has_sentiment = build_concept_info(doc)
    page = PageData(
        title=title,
        lang=lang,
        subtitle=doc.subtitle or "",
        sentences=sentence_views(doc, concepts),
        concepts=concepts,
        doc_stats=doc_stats,
        genre=doc.genre,
        has_sentiment=has_sentiment,
    )
    lang_dir = outdir / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    html_path = lang_dir / f"{doc.doc}-view.html"
    html_path.write_text(render_html(page, "../assets", "../index.html"), encoding="utf-8")
    logger.info("  → %s", html_path)

    json_path = write_doc_json(doc, outdir)
    logger.info("  → %s", json_path)

    return {
        "title": title,
        "subtitle": doc.subtitle or "",
        "path": f"{lang}/{doc.doc}-view.html",
        "sent_count": len(doc),
        "tag_pct": tag_pct,
        "corpus_id": _corpus_id(corpus_db, docid),
        "has_sentiment": has_sentiment,
    }


def _corpus_id(corpus_db: str, docid: int) -> Optional[int]:
    """The corpusID of a document, for grouping in the index."""
    conn = sqlite3.connect(corpus_db)
    try:
        row = conn.execute("SELECT corpusID FROM doc WHERE docid = ?", (docid,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def get_corpus_map(corpus_db: str) -> dict[int, str]:
    """Return {corpusID: title} for all corpora in the database.

    Args:
        corpus_db: Path to the language corpus database.

    Returns:
        Mapping from corpus ID to corpus title.
    """
    conn = sqlite3.connect(corpus_db)
    try:
        rows = conn.execute(
            "SELECT corpusID, title FROM corpus ORDER BY corpusID"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


def save_lang_sidecar(
    lang: str, docs: list[dict], outdir: Path, corpus_map: dict[int, str]
) -> None:
    """Save per-language metadata sidecar for combined index.

    Written to display/{lang}/index.json so multiple language runs accumulate.

    Args:
        lang: Language code.
        docs: List of document metadata dicts.
        outdir: Root output directory.
        corpus_map: {corpusID: title} mapping for corpus grouping.
    """
    sidecar = {"lang": lang, "docs": docs, "corpora": corpus_map}
    sidecar_path = outdir / lang / "index.json"
    sidecar_path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")


def write_doc_json(doc: Document, outdir: Path) -> Path:
    """Write the per-document JSON Lines record.

    One line in the corpus JSON format (docs/corpus-model.md), without
    annotator names, comments or candidate lists, written to
    ``outdir/data/docs/{lang}-{genre}-{docname}.jsonl``.  The three-part
    filename enables shell-level consolidation without JSON parsing::

        cat docs/eng-*.jsonl           # all English
        cat docs/*-stories-*.jsonl     # all stories, any language
        cat docs/*.jsonl               # full corpus

    Args:
        doc: The document.
        outdir: Root output directory (e.g. ``display/``).

    Returns:
        Path to the written JSONL file.
    """
    docs_dir = outdir / "data" / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    genre = doc.genre or "other"
    out_path = docs_dir / f"{doc.language}-{genre}-{doc.doc}.jsonl"
    out_path.write_text(jsonl.dumps(doc, slim=True) + "\n", encoding="utf-8")
    return out_path


def write_consolidated_json(outdir: Path) -> None:
    """Write consolidated NDJSON files by language, genre, and full corpus.

    Reads all per-document JSONL files from ``outdir/data/docs/`` and writes:

    - ``outdir/data/lang/{lang}.jsonl``
    - ``outdir/data/genre/{genre}.jsonl``
    - ``outdir/data/corpus.jsonl``

    These are equivalent to the shell ``cat`` commands that the filename
    pattern already enables, but generated for convenience.

    Args:
        outdir: Root output directory (e.g. ``display/``).
    """
    docs_dir = outdir / "data" / "docs"
    if not docs_dir.exists():
        logger.warning("No docs/ directory found — run document generation first.")
        return

    doc_files = sorted(docs_dir.glob("*.jsonl"))
    if not doc_files:
        logger.warning("No per-document JSONL files found in %s", docs_dir)
        return

    lang_dir = outdir / "data" / "lang"
    genre_dir = outdir / "data" / "genre"
    lang_dir.mkdir(parents=True, exist_ok=True)
    genre_dir.mkdir(parents=True, exist_ok=True)

    lang_lines: dict[str, list[str]] = {}
    genre_lines: dict[str, list[str]] = {}
    all_lines: list[str] = []

    for doc_file in doc_files:
        line = doc_file.read_text(encoding="utf-8").strip()
        if not line:
            continue
        # filename is {lang}-{genre}-{docname}.jsonl — no JSON parse needed
        parts = doc_file.stem.split("-", 2)
        if len(parts) < 2:
            logger.warning("Unexpected filename format, skipping: %s", doc_file)
            continue
        ll, genre = parts[0], parts[1]
        lang_lines.setdefault(ll, []).append(line)
        genre_lines.setdefault(genre, []).append(line)
        all_lines.append(line)

    for ll, lines in sorted(lang_lines.items()):
        p = lang_dir / f"{ll}.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(
            "  lang/%s.jsonl: %d docs (%.0fKB)", ll, len(lines), p.stat().st_size / 1024
        )

    for genre, lines in sorted(genre_lines.items()):
        p = genre_dir / f"{genre}.jsonl"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info(
            "  genre/%s.jsonl: %d docs (%.0fKB)", genre, len(lines), p.stat().st_size / 1024
        )

    corpus_path = outdir / "data" / "corpus.jsonl"
    corpus_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    logger.info(
        "corpus.jsonl: %d docs (%.0fKB)", len(all_lines), corpus_path.stat().st_size / 1024
    )


def write_index(outdir: Path) -> None:
    """Write combined index.html from all per-language sidecar files.

    Scans outdir for any {lang}/index.json files written by previous runs,
    so each language run accumulates into one combined index.

    Args:
        outdir: Root output directory.
    """
    unsorted: dict[str, dict] = {}
    for sidecar_path in sorted(outdir.glob("*/index.json")):
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            lang = data.get("lang", sidecar_path.parent.name)
            docs = data.get("docs", [])
            corpora = data.get("corpora", {})
            if docs:
                grouped: dict[str, list[dict]] = {}
                for doc in docs:
                    cid = doc.get("corpus_id")
                    corpus_title = corpora.get(str(cid), "Other") if cid else "Other"
                    grouped.setdefault(corpus_title, []).append(doc)
                unsorted[lang] = {"groups": grouped, "doc_count": len(docs)}
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Skipping sidecar %s: %s", sidecar_path, exc)

    by_lang = dict(sorted(unsorted.items(), key=lambda x: -x[1]["doc_count"]))

    lang_names = {lang: LANG_NAMES.get(lang, lang) for lang in by_lang}

    # Compute summary statistics for the index header
    total_docs = sum(info["doc_count"] for info in by_lang.values())
    total_sents = sum(
        doc.get("sent_count", 0)
        for info in by_lang.values()
        for docs in info["groups"].values()
        for doc in docs
    )
    total_sents_str = f"{total_sents:,}"

    tmpl = _get_env().get_template("index.html")
    html = tmpl.render(
        by_lang=by_lang,
        lang_names=lang_names,
        n_langs=len(by_lang),
        total_docs=total_docs,
        total_sents=total_sents_str,
    )
    index_path = outdir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    langs_str = ", ".join(by_lang) if by_lang else "(none)"
    logger.info("Index → %s  [%s]", index_path, langs_str)


# ---------------------------------------------------------------------------
# Shared data file generation
# ---------------------------------------------------------------------------


def read_all_link_dbs() -> dict[tuple[str, str], dict[int, list[int]]]:
    """Read all link databases and return bidirectional slink mappings.

    Returns:
        {(src_lang, tgt_lang): {src_sid: [tgt_sids]}} for both directions
        of each link database found in BUILD_DIR.
    """
    links: dict[tuple[str, str], dict[int, list[int]]] = {}

    for db_path in sorted(BUILD_DIR.glob("*-*.db")):
        parts = db_path.stem.split("-")
        if len(parts) != 2:
            continue
        l1, l2 = parts
        if l1.startswith("wn"):
            continue

        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT fsid, tsid FROM slink").fetchall()
            conn.close()
        except sqlite3.OperationalError:
            continue

        if not rows:
            continue

        fwd: dict[int, list[int]] = {}
        rev: dict[int, list[int]] = {}
        for fsid, tsid in rows:
            fwd.setdefault(fsid, []).append(tsid)
            rev.setdefault(tsid, []).append(fsid)

        links[(l1, l2)] = fwd
        links[(l2, l1)] = rev
        logger.info("  %s: %d direct links", db_path.name, len(rows))

    return links


def cross_compile_slinks(
    direct: dict[tuple[str, str], dict[int, list[int]]],
) -> dict[tuple[str, str], dict[int, list[int]]]:
    """Add cross-compiled slinks via shared pivot languages.

    For each pair of languages (A, B) not directly linked, finds a pivot
    language P such that A→P and P→B both exist, and computes A→B.

    Args:
        direct: Direct slink mappings from read_all_link_dbs().

    Returns:
        All links (direct + cross-compiled).
    """
    all_links = dict(direct)
    all_langs = {lang for pair in direct for lang in pair}

    for l1 in sorted(all_langs):
        for l2 in sorted(all_langs):
            if l1 == l2 or (l1, l2) in all_links:
                continue
            for pivot in sorted(all_langs):
                if pivot == l1 or pivot == l2:
                    continue
                l1_to_p = direct.get((l1, pivot))
                p_to_l2 = direct.get((pivot, l2))
                if not l1_to_p or not p_to_l2:
                    continue
                cross: dict[int, list[int]] = {}
                for l1_sid, p_sids in l1_to_p.items():
                    for p_sid in p_sids:
                        if p_sid in p_to_l2:
                            cross.setdefault(l1_sid, []).extend(
                                p_to_l2[p_sid]
                            )
                if cross:
                    all_links[(l1, l2)] = cross
                    n = sum(len(v) for v in cross.values())
                    logger.info(
                        "  %s→%s: %d cross-compiled links (via %s)",
                        l1, l2, n, pivot,
                    )
                break

    return all_links


def collect_used_synsets() -> set[str]:
    """Collect all synset IDs used as concept tags in any corpus database.

    Returns:
        Set of synset ID strings.
    """
    used: set[str] = set()
    for db_path in sorted(BUILD_DIR.glob("*.db")):
        if db_path.stem.startswith("wn") or "-" in db_path.stem:
            continue
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                "SELECT DISTINCT tag FROM concept"
                " WHERE tag IS NOT NULL AND tag != ''"
                " AND tag NOT IN ('x','w','e','per','num','dat','org','oth')"
            ).fetchall()
            used.update(r[0] for r in rows)
            conn.close()
        except sqlite3.OperationalError:
            continue
    return used


def build_data_files(outdir: Path, wn_db: str) -> None:
    """Build shared JSON data files for dynamic language loading.

    Generates slinks.json, sent-{lang}.json, wn-defs-{lang}.json,
    wn-syns-{lang}.json, and manifest.json in outdir/data/.

    Args:
        outdir: Root output directory (e.g. display/).
        wn_db: Path to wn-ntumc.db.
    """
    data_dir = outdir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # --- Sentence links ---
    logger.info("Reading link databases...")
    direct_links = read_all_link_dbs()
    all_links = cross_compile_slinks(direct_links)

    slinks_json: dict[str, dict[str, dict[str, list[int]]]] = {}
    needed_sids: dict[str, set[int]] = {}

    for (src, tgt), mapping in sorted(all_links.items()):
        slinks_json.setdefault(src, {})[tgt] = {
            str(k): v for k, v in mapping.items()
        }
        needed_sids.setdefault(tgt, set())
        for tgt_sids in mapping.values():
            needed_sids[tgt].update(tgt_sids)

    slinks_path = data_dir / "slinks.json"
    slinks_path.write_text(
        json.dumps(slinks_json, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    logger.info(
        "slinks.json → %s (%.0fKB)",
        slinks_path, slinks_path.stat().st_size / 1024,
    )

    # --- Sentence text per language ---
    for lang, sids in sorted(needed_sids.items()):
        corpus_db = BUILD_DIR / f"{lang}.db"
        if not corpus_db.exists():
            logger.warning("Corpus DB not found for %s, skipping", lang)
            continue
        conn = sqlite3.connect(str(corpus_db))
        # filtered here, not in SQL: there can be more ids than SQLite takes as variables
        rows = conn.execute("SELECT sid, sent FROM sent ORDER BY sid").fetchall()
        conn.close()
        sent_data = {str(r[0]): r[1] for r in rows if r[0] in sids}
        sent_path = data_dir / f"sent-{lang}.json"
        sent_path.write_text(
            json.dumps(sent_data, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        logger.info(
            "  sent-%s.json: %d sentences (%.0fKB)",
            lang, len(sent_data), sent_path.stat().st_size / 1024,
        )

    # --- WordNet definitions and synonyms ---
    logger.info("Extracting WordNet data...")
    used_synsets = collect_used_synsets()
    logger.info("  %d unique synsets across all corpora", len(used_synsets))

    wn_conn = sqlite3.connect(wn_db)
    synset_list = sorted(used_synsets)
    ph = ",".join("?" * len(synset_list))

    def_langs_avail: list[str] = []
    syn_langs_avail: list[str] = []

    # Find which languages have data
    def_lang_rows = wn_conn.execute(
        f"SELECT DISTINCT lang FROM synset_def WHERE synset IN ({ph})",
        synset_list,
    ).fetchall()
    syn_lang_rows = wn_conn.execute(
        f"SELECT DISTINCT lang FROM sense WHERE synset IN ({ph})",
        synset_list,
    ).fetchall()

    for (lang,) in sorted(def_lang_rows):
        rows = wn_conn.execute(
            f"SELECT synset, def FROM synset_def"
            f" WHERE lang=? AND synset IN ({ph})"
            f" ORDER BY synset, sid",
            [lang] + synset_list,
        ).fetchall()
        defs: dict[str, str] = {}
        for synset, defn in rows:
            if synset in defs:
                defs[synset] += "; " + defn
            else:
                defs[synset] = defn
        if not defs:
            continue
        def_path = data_dir / f"wn-defs-{lang}.json"
        def_path.write_text(
            json.dumps(defs, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        def_langs_avail.append(lang)
        logger.info(
            "  wn-defs-%s.json: %d defs (%.0fKB)",
            lang, len(defs), def_path.stat().st_size / 1024,
        )

    for (lang,) in sorted(syn_lang_rows):
        rows = wn_conn.execute(
            f"SELECT s.synset, w.lemma FROM sense s"
            f" JOIN word w ON s.wordid = w.wordid"
            f" WHERE s.lang=? AND s.synset IN ({ph})"
            f" ORDER BY s.synset, s.confidence DESC, s.freq DESC",
            [lang] + synset_list,
        ).fetchall()
        syns: dict[str, list[str]] = {}
        for synset, lemma in rows:
            syns.setdefault(synset, []).append(lemma)
        if not syns:
            continue
        syn_path = data_dir / f"wn-syns-{lang}.json"
        syn_path.write_text(
            json.dumps(syns, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        syn_langs_avail.append(lang)
        logger.info(
            "  wn-syns-%s.json: %d synsets (%.0fKB)",
            lang, len(syns), syn_path.stat().st_size / 1024,
        )

    wn_conn.close()

    # --- Translation pairs available from each language ---
    trans_avail: dict[str, list[str]] = {}
    for src, tgt in sorted(all_links.keys()):
        trans_avail.setdefault(src, []).append(tgt)

    # --- Manifest ---
    manifest = {
        "lang_names": LANG_NAMES,
        "ne_defs": NAMED_ENTITY_DEFS,
        "defs": sorted(def_langs_avail),
        "syns": sorted(syn_langs_avail),
        "trans": trans_avail,
    }
    manifest_path = data_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("manifest.json → %s", manifest_path)


# ---------------------------------------------------------------------------
# Genre summary page
# ---------------------------------------------------------------------------

def collect_genre_stats() -> dict[tuple[str, str], dict[str, int]]:
    """Collect per-genre, per-language statistics from all corpus databases.

    Reads the ``corpus`` column from the corpus table to classify each
    corpus into a genre via CORPUS_CODE_TO_GENRE.

    Returns:
        {(genre, lang): {docs, sents, words, concepts}} for every
        genre/language combination that has data.
    """
    stats: dict[tuple[str, str], dict[str, int]] = {}

    for db_path in sorted(BUILD_DIR.glob("*.db")):
        if db_path.stem.startswith("wn") or "-" in db_path.stem:
            continue
        lang = db_path.stem
        try:
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                """
                SELECT
                    cr.genre,
                    COUNT(DISTINCT d.docid),
                    COUNT(DISTINCT s.sid),
                    COUNT(DISTINCT s.sid || ':' || CAST(w.wid AS TEXT)),
                    COUNT(DISTINCT CASE
                        WHEN c.tag IS NOT NULL AND c.tag != ''
                             AND c.tag NOT IN ('x','w','e')
                        THEN c.sid || ':' || CAST(c.cid AS TEXT)
                    END)
                FROM doc d
                JOIN corpus cr ON cr.corpusID = d.corpusID
                JOIN sent s ON s.docID = d.docid
                JOIN word w ON w.sid = s.sid
                LEFT JOIN concept c ON c.sid = s.sid
                GROUP BY cr.genre
                """
            ).fetchall()
            conn.close()
        except sqlite3.OperationalError:
            continue

        for genre, docs, sents, words, concepts in rows:
            if genre not in GENRE_NAMES:
                continue
            key = (genre, lang)
            if key in stats:
                s = stats[key]
                s["docs"] += docs
                s["sents"] += sents
                s["words"] += words
                s["concepts"] += concepts
            else:
                stats[key] = {
                    "docs": docs,
                    "sents": sents,
                    "words": words,
                    "concepts": concepts,
                }

    return stats


def _sum_stats(items: list[dict[str, int]]) -> dict[str, int]:
    """Sum a list of stat dicts."""
    out = {"docs": 0, "sents": 0, "words": 0, "concepts": 0}
    for s in items:
        for k in out:
            out[k] += s.get(k, 0)
    return out


def write_summary(outdir: Path) -> None:
    """Write the genre summary HTML page.

    Args:
        outdir: Root output directory (e.g. display/).
    """
    logger.info("Collecting genre statistics...")
    stats = collect_genre_stats()

    if not stats:
        logger.warning("No genre statistics found — skipping summary page.")
        return

    # Which languages have data, sorted by total docs descending
    lang_docs: dict[str, int] = {}
    for (genre, lang), s in stats.items():
        lang_docs[lang] = lang_docs.get(lang, 0) + s["docs"]
    languages = sorted(lang_docs, key=lambda l: -lang_docs[l])

    # Per-genre totals
    totals_by_genre: dict[str, dict[str, int]] = {}
    for genre in GENRE_ORDER:
        items = [s for (g, _), s in stats.items() if g == genre]
        totals_by_genre[genre] = _sum_stats(items)

    # Per-language totals
    totals_by_lang: dict[str, dict[str, int]] = {}
    for lang in languages:
        items = [s for (_, l), s in stats.items() if l == lang]
        totals_by_lang[lang] = _sum_stats(items)

    # Grand total
    grand = _sum_stats(list(stats.values()))

    empty = {"docs": 0, "sents": 0, "words": 0, "concepts": 0}

    tmpl = _get_env().get_template("summary.html")
    html = tmpl.render(
        languages=languages,
        lang_names=LANG_NAMES,
        genre_order=GENRE_ORDER,
        genre_names=GENRE_NAMES,
        stats=stats,
        totals_by_genre=totals_by_genre,
        totals_by_lang=totals_by_lang,
        grand=grand,
        empty=empty,
    )
    summary_path = outdir / "summary.html"
    summary_path.write_text(html, encoding="utf-8")
    logger.info("Summary → %s", summary_path)


# ---------------------------------------------------------------------------
# About page
# ---------------------------------------------------------------------------

def write_about(outdir: Path) -> None:
    """Write the about page, populating language stats from sidecars.

    Args:
        outdir: Root output directory (e.g. display/).
    """
    lang_docs: dict[str, int] = {}
    lang_sents: dict[str, str] = {}

    for sidecar_path in sorted(outdir.glob("*/index.json")):
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            lang = data.get("lang", sidecar_path.parent.name)
            docs = data.get("docs", [])
            lang_docs[lang] = len(docs)
            total = sum(d.get("sent_count", 0) for d in docs)
            lang_sents[lang] = f"{total:,}"
        except (json.JSONDecodeError, OSError):
            continue

    languages = sorted(lang_docs, key=lambda l: -lang_docs[l])

    tmpl = _get_env().get_template("about.html")
    html = tmpl.render(
        languages=languages,
        lang_names=LANG_NAMES,
        lang_docs=lang_docs,
        lang_sents=lang_sents,
    )
    about_path = outdir / "about.html"
    about_path.write_text(html, encoding="utf-8")
    logger.info("About → %s", about_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate static HTML corpus display pages."
    )
    parser.add_argument(
        "--lang", default="eng", help="Language corpus to use (default: eng)"
    )
    parser.add_argument("--outdir", default="display", help="Output directory")
    parser.add_argument(
        "--corpus-db", help="Path to corpus DB (default: build/{lang}.db)"
    )
    parser.add_argument(
        "--wn-db", default=None, help="Path to WN DB (default: build/wn-ntumc.db)"
    )
    parser.add_argument(
        "--tagged",
        action="store_true",
        help="Only include documents with >= --min-tagged fraction of words tagged",
    )
    parser.add_argument(
        "--min-tagged",
        type=float,
        default=0.5,
        metavar="FRAC",
        help="Minimum tagging fraction for --tagged filter (default: 0.5)",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc", help="Document name (e.g. spec)")
    group.add_argument("--docid", type=int, help="Document ID")
    group.add_argument(
        "--all", action="store_true", help="Process all documents in the corpus"
    )
    group.add_argument(
        "--build-data",
        action="store_true",
        help="Build shared data files (slinks, sentences, WN) only",
    )
    group.add_argument(
        "--build-summary",
        action="store_true",
        help="Build genre summary page only",
    )
    group.add_argument(
        "--build-about",
        action="store_true",
        help="Build about page only",
    )
    group.add_argument(
        "--build-pages",
        action="store_true",
        help="Build all non-document pages (index, summary, about)",
    )
    group.add_argument(
        "--build-json",
        action="store_true",
        help="Build consolidated NDJSON files (lang/, genre/, corpus.jsonl) from per-doc annotations",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    wn_db = args.wn_db or str(BUILD_DIR / "wn-ntumc.db")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # --build-data: generate shared JSON files and exit
    if args.build_data:
        if not Path(wn_db).exists():
            logger.error("WordNet database not found: %s", wn_db)
            sys.exit(1)
        build_data_files(outdir, wn_db)
        return

    # --build-summary: generate genre summary page and exit
    if args.build_summary:
        write_summary(outdir)
        return

    # --build-about: generate about page and exit
    if args.build_about:
        write_about(outdir)
        return

    # --build-pages: generate all non-document pages and exit
    if args.build_pages:
        write_index(outdir)
        write_summary(outdir)
        write_about(outdir)
        return

    # --build-json: consolidate per-document NDJSON files and exit
    if args.build_json:
        write_consolidated_json(outdir)
        return

    corpus_db = args.corpus_db or str(BUILD_DIR / f"{args.lang}.db")

    if not Path(corpus_db).exists():
        logger.error("Database not found: %s", corpus_db)
        sys.exit(1)

    # Resolve tagging rates (needed for filter and index display)
    tag_rates: dict[int, float] = {}
    if args.tagged or args.all:
        logger.info("Computing tagging rates...")
        tag_rates = get_doc_tagging_rates(corpus_db)
        if tag_rates:
            rates = sorted(tag_rates.values())
            logger.info(
                "Tagging rates: min=%.0f%% median=%.0f%% max=%.0f%%",
                rates[0] * 100,
                rates[len(rates) // 2] * 100,
                rates[-1] * 100,
            )

    # Resolve which docs to process
    if args.all:
        conn = sqlite3.connect(corpus_db)
        rows = conn.execute("SELECT docid FROM doc ORDER BY docid").fetchall()
        conn.close()
        docids = [r[0] for r in rows]
        if args.tagged:
            before = len(docids)
            min_tagged = args.min_tagged
            if tag_rates:
                max_rate = max(tag_rates.values())
                if max_rate == 0.0:
                    logger.warning(
                        "Language '%s' has no tagged words — skipping.", args.lang
                    )
                    docids = []
                elif max_rate < min_tagged:
                    min_tagged = min(
                        r for r in tag_rates.values() if r > 0.0
                    )
                    logger.info(
                        "Max tagging rate %.0f%% < %.0f%% threshold; "
                        "auto-lowering to %.0f%% (all tagged docs)",
                        max_rate * 100,
                        args.min_tagged * 100,
                        min_tagged * 100,
                    )
            docids = [d for d in docids if tag_rates.get(d, 0.0) >= min_tagged]
            logger.info(
                "Filtered %d → %d docs (>= %.0f%% tagged)",
                before,
                len(docids),
                min_tagged * 100,
            )
    elif args.doc:
        conn = sqlite3.connect(corpus_db)
        row = conn.execute("SELECT docid FROM doc WHERE doc = ?", (args.doc,)).fetchone()
        conn.close()
        docid = row[0] if row else None
        if docid is None:
            logger.error("Document '%s' not found in %s", args.doc, corpus_db)
            sys.exit(1)
        docids = [docid]
    else:
        docids = [args.docid]

    lang_docs: list[dict] = []

    for docid in docids:
        meta = write_document(
            corpus_db, docid, outdir, args.lang, tag_rate=tag_rates.get(docid)
        )
        if meta:
            lang_docs.append(meta)

    if lang_docs:
        lang_dir = outdir / args.lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        corpus_map = get_corpus_map(corpus_db)
        save_lang_sidecar(args.lang, lang_docs, outdir, corpus_map)

    write_index(outdir)
    logger.info("Done. %d document(s) generated.", len(lang_docs))


if __name__ == "__main__":
    main()
