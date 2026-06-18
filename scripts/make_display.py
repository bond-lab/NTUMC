#!/usr/bin/env python3
"""Generate static HTML corpus display pages for NTUMC documents.

Each document produces three files in OUTDIR/{lang}/:
  {doc}-view.html      — readable HTML page
  {doc}-concepts.json  — word → concept mappings
  {doc}-synsets.json   — synset definitions and synonyms

Usage:
    .venv/bin/python scripts/make_display.py --lang eng --doc spec --outdir display/
    .venv/bin/python scripts/make_display.py --lang eng --docid 440 --outdir display/
    .venv/bin/python scripts/make_display.py --lang eng --all --outdir display/
"""

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader
from markupsafe import Markup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ntumc.db.corpus import Corpus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

NAMED_ENTITY_DEFS: dict[str, str] = {
    "per": "Person Name",
    "num": "Number",
    "dat": "Date",
    "org": "Organisation Name",
    "oth": "Other Name",
}
SKIP_TAGS: frozenset[str] = frozenset({"x", "w", "e"})
VALID_STYPES: frozenset[str] = frozenset(
    {"h1", "h2", "h3", "h4", "h5", "h6", "h7", "p"}
)

# ---------------------------------------------------------------------------
# Jinja2 HTML template
# ---------------------------------------------------------------------------

TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{ title }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
  <link rel="stylesheet" href="{{ assets_path }}/corpus.css">
</head>
<body class="bg-light">

<!-- Settings Modal -->
<div class="modal fade" id="settingsModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">Display Settings</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="showWordIdToggle">
          <label class="form-check-label" for="showWordIdToggle">Show word IDs</label>
        </div>
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" id="showSynsToggle" checked>
          <label class="form-check-label" for="showSynsToggle">Show synonyms</label>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        <button type="button" class="btn btn-primary" id="saveSettings">Save</button>
      </div>
    </div>
  </div>
</div>

<div class="container mt-4 mb-5">
  <div class="d-flex justify-content-between align-items-start mb-3">
    <div>
      <h1 class="h4 mb-1">{{ title }}</h1>
      {%- if subtitle %}<p class="text-muted small mb-1">{{ subtitle }}</p>{% endif %}
      <a href="{{ index_path }}" class="text-muted small text-decoration-none">
        <i class="bi bi-arrow-left"></i> All documents
      </a>
    </div>
    <i id="settingsIcon" class="bi bi-gear mt-1" title="Settings"
       data-bs-toggle="modal" data-bs-target="#settingsModal"></i>
  </div>

  <div class="card shadow-sm">
    <div class="card-body" id="story">
{%- for sent in sentences %}
{%- if sent.stype == 'h1' %}<h1>
{%- elif sent.stype == 'h2' %}<h2>
{%- elif sent.stype == 'h3' %}<h3>
{%- elif sent.stype == 'h4' %}<h4>
{%- elif sent.stype == 'h5' %}<h5>
{%- elif sent.stype == 'h6' %}<h6>
{%- elif sent.stype == 'h7' %}<h7>
{%- elif sent.stype == 'p' %}
<p>
{%- endif %}
<span class="sent" id="s{{ sent.sid }}">{%- for w in sent.words -%}
{%- set cids = sent.word_cids.get(w.wid) -%}
<span class="word" id="w{{ sent.sid }}:{{ w.wid }}"
  data-pos="{{ w.pos }}" data-lemma="{{ w.lemma }}"
  {%- if cids %} data-cids="{{ cids|join(' ') }}"{% endif %}>{{ w.word }}</span> {% endfor %}</span>
{%- if sent.stype == 'h1' %}</h1>
{%- elif sent.stype == 'h2' %}</h2>
{%- elif sent.stype == 'h3' %}</h3>
{%- elif sent.stype == 'h4' %}</h4>
{%- elif sent.stype == 'h5' %}</h5>
{%- elif sent.stype == 'h6' %}</h6>
{%- elif sent.stype == 'h7' %}</h7>
{%- endif %}
{%- endfor %}
    </div>
  </div>
</div>

<!-- Tooltip card -->
<div id="tooltip" class="card shadow" style="display:none;position:absolute;z-index:1070;max-width:340px">
  <div class="card-body py-2 px-3">
    <div id="tooltipContent"></div>
    <div class="d-flex justify-content-end mt-1">
      <i id="copyBtn" class="bi bi-clipboard tooltip-icon" title="Copy"></i>
      <i id="closeBtn" class="bi bi-x-lg tooltip-icon" title="Close"></i>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
  /* Data embedded inline so the page works from file:// without a server */
  var conceptInfo = {{ concepts_data }};
  var synsetInfo  = {{ synsets_data }};
</script>
<script src="{{ assets_path }}/corpus-view.js"></script>
</body>
</html>
"""

INDEX_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NTUMC Corpus Display</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
<div class="container mt-4 mb-5">
  <h1 class="h3 mb-4">NTUMC Corpus Documents</h1>
  {%- for lang, docs in by_lang.items() %}
  <h2 class="h5 mt-4 mb-2 text-uppercase text-muted">{{ lang }}</h2>
  <div class="list-group mb-3">
    {%- for doc in docs %}
    <a href="{{ doc.path }}" class="list-group-item list-group-item-action d-flex justify-content-between align-items-start">
      <div>
        <div>{{ doc.title }}</div>
        {%- if doc.subtitle %}<small class="text-muted">{{ doc.subtitle }}</small>{% endif %}
      </div>
      <small class="text-muted ms-3 text-nowrap">{{ doc.sent_count }} sent.</small>
    </a>
    {%- endfor %}
  </div>
  {%- endfor %}
</div>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def build_concept_info(doc_data: dict) -> dict:
    """Extract concept info and annotate each sentence with word_cids.

    Mutates each sentence dict in doc_data to add a ``word_cids`` key
    ({wid: [concept_key, ...]}).  Returns the flat concepts dict.

    Args:
        doc_data: Document dict from Corpus.get_doc().

    Returns:
        concepts: {concept_key: {lemma, synset, wids}}
    """
    concepts: dict = {}

    for sent in doc_data["sentences"]:
        sid = sent["sid"]
        word_cids: dict[int, list[str]] = {}

        for concept in sent.get("concepts", []):
            tag = concept.get("tag") or ""
            if not tag or tag in SKIP_TAGS:
                continue

            cid = concept["cid"]
            key = f"c{sid}:{cid}"
            wids: list[int] = concept.get("wids", [])

            concepts[key] = {
                "lemma": concept.get("clemma", ""),
                "synset": tag,
                "wids": wids,
            }

            for wid in wids:
                word_cids.setdefault(wid, []).append(key)

        sent["word_cids"] = word_cids

    return concepts


def build_synset_info(wn_db_path: str, synset_ids: set[str]) -> dict:
    """Fetch definitions and English synonyms for a set of synset IDs.

    Args:
        wn_db_path: Path to wn-ntumc.db.
        synset_ids: All tag values collected from concepts (includes NE tags).

    Returns:
        {synset_id: {def, syns, pos}}
    """
    result: dict = {}
    named = {s for s in synset_ids if s in NAMED_ENTITY_DEFS}
    regular = {s for s in synset_ids if s not in NAMED_ENTITY_DEFS and s}

    for tag in named:
        result[tag] = {"def": NAMED_ENTITY_DEFS[tag], "syns": [], "pos": ""}

    if not regular:
        return result

    conn = sqlite3.connect(wn_db_path)
    conn.row_factory = sqlite3.Row
    try:
        ph = ",".join("?" * len(regular))
        params = list(regular)

        defs: dict[str, list[str]] = {}
        for row in conn.execute(
            f"SELECT synset, def FROM synset_def"
            f" WHERE synset IN ({ph}) AND lang='eng' ORDER BY synset, sid",
            params,
        ):
            defs.setdefault(row["synset"], []).append(row["def"])

        syns: dict[str, list[str]] = {}
        for row in conn.execute(
            f"SELECT s.synset, w.lemma FROM sense s"
            f" JOIN word w ON s.wordid = w.wordid"
            f" WHERE s.synset IN ({ph}) AND s.lang = 'eng'"
            f" ORDER BY s.synset, s.confidence DESC, s.freq DESC",
            params,
        ):
            syns.setdefault(row["synset"], []).append(row["lemma"])

        pos_map: dict[str, str] = {}
        for row in conn.execute(
            f"SELECT synset, pos FROM synset WHERE synset IN ({ph})",
            params,
        ):
            pos_map[row["synset"]] = row["pos"]

        for synset_id in regular:
            result[synset_id] = {
                "def": "; ".join(defs.get(synset_id, [])),
                "syns": syns.get(synset_id, []),
                "pos": pos_map.get(synset_id, ""),
            }
    finally:
        conn.close()

    return result


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def render_html(
    doc_data: dict,
    concepts: dict,
    synsets: dict,
    assets_path: str,
    index_path: str,
) -> str:
    """Render the document HTML page with data embedded inline.

    JSON data is embedded directly in the HTML so the page works from
    file:// without needing a local web server.

    Args:
        doc_data: Document dict (sentences already annotated with word_cids).
        concepts: Concepts dict to embed as JavaScript.
        synsets: Synsets dict to embed as JavaScript.
        assets_path: Relative path from HTML file to the assets/ directory.
        index_path: Relative path to the index HTML file.

    Returns:
        Rendered HTML string.
    """
    env = Environment(loader=BaseLoader(), autoescape=True)
    tmpl = env.from_string(TEMPLATE)
    return tmpl.render(
        title=doc_data.get("title") or "",
        subtitle=doc_data.get("subtitle") or "",
        sentences=doc_data["sentences"],
        assets_path=assets_path,
        index_path=index_path,
        # Mark JSON strings as safe so Jinja2 doesn't escape them
        concepts_data=Markup(json.dumps(concepts, ensure_ascii=False)),
        synsets_data=Markup(json.dumps(synsets, ensure_ascii=False)),
    )


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------


def write_document(
    corpus_db: str,
    wn_db: str,
    docid: int,
    outdir: Path,
    lang: str,
) -> Optional[dict]:
    """Generate all output files for one document.

    Args:
        corpus_db: Path to the language corpus database.
        wn_db: Path to wn-ntumc.db.
        docid: Document ID to process.
        outdir: Root output directory (e.g. display/).
        lang: Language code (e.g. 'eng').

    Returns:
        Dict with doc metadata for index generation, or None on failure.
    """
    corpus = Corpus(corpus_db)
    doc_data = corpus.get_doc(docid)
    if not doc_data:
        logger.error("Document %d not found in %s", docid, corpus_db)
        return None

    doc_name = doc_data.get("doc") or f"doc{docid}"
    title = doc_data.get("title") or doc_name
    subtitle = doc_data.get("subtitle") or ""
    n_sents = len(doc_data.get("sentences", []))
    logger.info("Processing '%s' (%d sentences)...", title, n_sents)

    concepts = build_concept_info(doc_data)

    synset_ids = {v["synset"] for v in concepts.values()}
    synsets = build_synset_info(wn_db, synset_ids)

    lang_dir = outdir / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    html_path = lang_dir / f"{doc_name}-view.html"

    html = render_html(
        doc_data,
        concepts=concepts,
        synsets=synsets,
        assets_path="../assets",
        index_path="../index.html",
    )
    html_path.write_text(html, encoding="utf-8")

    logger.info("  → %s", html_path)
    return {
        "title": title,
        "subtitle": subtitle,
        "path": f"{lang}/{doc_name}-view.html",
        "sent_count": n_sents,
    }


def write_index(by_lang: dict[str, list[dict]], outdir: Path) -> None:
    """Write the landing-page index.html.

    Args:
        by_lang: {lang: [doc_meta_dicts]}
        outdir: Root output directory.
    """
    env = Environment(loader=BaseLoader(), autoescape=True)
    tmpl = env.from_string(INDEX_TEMPLATE)
    html = tmpl.render(by_lang=by_lang)
    index_path = outdir / "index.html"
    index_path.write_text(html, encoding="utf-8")
    logger.info("Index → %s", index_path)


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
        "--corpus-db",
        help="Path to corpus DB (default: build/{lang}.db)",
    )
    parser.add_argument(
        "--wn-db",
        default=None,
        help="Path to WN DB (default: build/wn-ntumc.db)",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--doc", help="Document name (e.g. spec)")
    group.add_argument("--docid", type=int, help="Document ID")
    group.add_argument(
        "--all", action="store_true", help="Process all documents in the corpus"
    )

    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()

    corpus_db = args.corpus_db or str(BUILD_DIR / f"{args.lang}.db")
    wn_db = args.wn_db or str(BUILD_DIR / "wn-ntumc.db")
    outdir = Path(args.outdir)

    for path in (corpus_db, wn_db):
        if not Path(path).exists():
            logger.error("Database not found: %s", path)
            sys.exit(1)

    corpus = Corpus(corpus_db)

    # Resolve which docs to process
    if args.all:
        conn = sqlite3.connect(corpus_db)
        rows = conn.execute(
            "SELECT docid FROM doc ORDER BY docid"
        ).fetchall()
        conn.close()
        docids = [r[0] for r in rows]
    elif args.doc:
        docid = corpus.get_docid_by_docname(args.doc)
        if docid is None:
            logger.error("Document '%s' not found in %s", args.doc, corpus_db)
            sys.exit(1)
        docids = [docid]
    else:
        docids = [args.docid]

    by_lang: dict[str, list[dict]] = {args.lang: []}

    for docid in docids:
        meta = write_document(corpus_db, wn_db, docid, outdir, args.lang)
        if meta:
            by_lang[args.lang].append(meta)

    write_index(by_lang, outdir)
    logger.info("Done. %d document(s) generated.", len(by_lang[args.lang]))


if __name__ == "__main__":
    main()
