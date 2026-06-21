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
from pathlib import Path
from typing import Optional

from jinja2 import Environment, BaseLoader
from markupsafe import Markup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ntumc.db.corpus import Corpus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

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

# ---------------------------------------------------------------------------
# HTML template
# Word elements use the custom <w> tag (saves ~220KB vs <span class="word">).
# Compact attribute names: data-p=POS, data-l=lemma, data-c=concept-ids,
#   data-ns=no-space-after (boolean, presence-only).
# JSON keys: concepts {l=lemma, s=synset, w=wids}, synsets {d=def, s=syns, p=pos}
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

<div class="modal fade" id="settingsModal" tabindex="-1" aria-hidden="true">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header">
      <h5 class="modal-title">Display Settings</h5>
      <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
    </div>
    <div class="modal-body">
      <div class="form-check form-switch mb-3">
        <input class="form-check-input" type="checkbox" id="showWordIdToggle">
        <label class="form-check-label" for="showWordIdToggle">Show word IDs</label>
      </div>
      <hr>
      <h6 class="mb-2"><i class="bi bi-translate me-1"></i>Language</h6>
      <div class="mb-2">
        <label class="form-label small mb-1" for="defLangSelect">Definition language</label>
        <select class="form-select form-select-sm" id="defLangSelect">
          <option value="">None</option>
        </select>
      </div>
      <div class="mb-2">
        <label class="form-label small mb-1" for="synLangSelect">Synonym language</label>
        <select class="form-select form-select-sm" id="synLangSelect">
          <option value="">None</option>
        </select>
      </div>
      <div class="mb-2">
        <label class="form-label small mb-1" for="transLangSelect">Sentence translation</label>
        <select class="form-select form-select-sm" id="transLangSelect">
          <option value="">None</option>
        </select>
      </div>
      <div id="langStatus" class="small text-muted mt-2"></div>
    </div>
    <div class="modal-footer">
      <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
      <button type="button" class="btn btn-primary" id="saveSettings">Save</button>
    </div>
  </div></div>
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
  <div class="card shadow-sm"><div class="card-body" id="story">
{%- for sent in sentences %}
{%- if sent.stype == 'h1' %}<h1>
{%- elif sent.stype == 'h2' %}<h2>
{%- elif sent.stype == 'h3' %}<h3>
{%- elif sent.stype == 'h4' %}<h4>
{%- elif sent.stype == 'h5' %}<h5>
{%- elif sent.stype == 'h6' %}<h6>
{%- elif sent.stype == 'h7' %}<h7>
{%- elif sent.stype == 'h0' %}<h2>
{%- elif sent.stype == 'author' %}<p class="stype-author">
{%- elif sent.stype == 'translator' %}<p class="stype-translator">
{%- elif sent.stype == 'item' %}<p class="stype-item">
{%- elif sent.stype == 'p' %}
<p>
{%- endif %}
<span class="sent" id="s{{ sent.sid }}">{%- for w in sent.words -%}
{%- set cids = sent.word_cids.get(w.wid) -%}
<w id="w{{ sent.sid }}:{{ w.wid }}" data-p="{{ w.pos }}" data-l="{{ w.lemma }}"{% if cids %} data-c="{{ cids|join(' ') }}"{% endif %}{% if w.nospace %} data-ns{% endif %}>{{ w.word }}</w>{% endfor %}<i class="bi bi-translate trans-icon" data-sid="{{ sent.sid }}" title="Show translation"></i></span>
{%- if sent.stype == 'h1' %}</h1>
{%- elif sent.stype == 'h2' %}</h2>
{%- elif sent.stype == 'h3' %}</h3>
{%- elif sent.stype == 'h4' %}</h4>
{%- elif sent.stype == 'h5' %}</h5>
{%- elif sent.stype == 'h6' %}</h6>
{%- elif sent.stype == 'h7' %}</h7>
{%- elif sent.stype == 'h0' %}</h2>
{%- endif %}
{%- endfor %}
  </div></div>
</div>

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
  var conceptInfo = {{ concepts_data }};
  var docLang = {{ doc_lang_json }};
  var dataPath = {{ data_path_json }};
  try { localStorage.setItem('ntumc-lang', docLang); } catch(e) {}
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
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css" rel="stylesheet">
  <style>
    .corpus-toggle { cursor: pointer; user-select: none; }
    .corpus-toggle .bi { transition: transform 0.15s; }
    .corpus-toggle.collapsed .bi-chevron-down { transform: rotate(-90deg); }
  </style>
</head>
<body class="bg-light">
<div class="container mt-4 mb-5">
  <h1 class="h3 mb-3">NTUMC Corpus Documents</h1>
  {%- if by_lang|length > 1 %}
  <ul class="nav nav-tabs mb-3" role="tablist">
    {%- for lang in by_lang %}
    <li class="nav-item" role="presentation">
      <button class="nav-link{% if loop.first %} active{% endif %}"
              id="tab-{{ lang }}" data-bs-toggle="tab"
              data-bs-target="#pane-{{ lang }}" type="button"
              role="tab">{{ lang_names[lang] }}
        <span class="badge bg-secondary ms-1">{{ by_lang[lang].doc_count }}</span></button>
    </li>
    {%- endfor %}
  </ul>
  {%- endif %}
  <div class="tab-content">
    {%- for lang, info in by_lang.items() %}
    <div class="tab-pane fade{% if loop.first %} show active{% endif %}"
         id="pane-{{ lang }}" role="tabpanel">
      {%- for corpus_title, docs in info.groups.items() %}
      <div class="mb-3">
        <div class="corpus-toggle d-flex align-items-center gap-2 mb-2"
             data-bs-toggle="collapse" data-bs-target="#grp-{{ lang }}-{{ loop.index }}"
             aria-expanded="true">
          <i class="bi bi-chevron-down"></i>
          <span class="h6 mb-0">{{ corpus_title }}</span>
          <span class="badge bg-secondary">{{ docs|length }}</span>
        </div>
        <div class="collapse show" id="grp-{{ lang }}-{{ loop.index }}">
          <div class="list-group">
            {%- for doc in docs %}
            <a href="{{ doc.path }}" class="list-group-item list-group-item-action">
              <div class="d-flex justify-content-between align-items-start">
                <div>
                  <div>{{ doc.title }}</div>
                  {%- if doc.subtitle %}<small class="text-muted">{{ doc.subtitle }}</small>{% endif %}
                </div>
                <small class="text-muted ms-3 text-nowrap">{{ doc.sent_count }} sent.
                  {%- if doc.tag_pct %} &middot; {{ doc.tag_pct }}% tagged{% endif %}</small>
              </div>
            </a>
            {%- endfor %}
          </div>
        </div>
      </div>
      {%- endfor %}
    </div>
    {%- endfor %}
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
document.querySelectorAll('.corpus-toggle').forEach(function(el) {
  var target = document.querySelector(el.getAttribute('data-bs-target'));
  if (!target) return;
  target.addEventListener('hide.bs.collapse', function() { el.classList.add('collapsed'); });
  target.addEventListener('show.bs.collapse', function() { el.classList.remove('collapsed'); });
});
(function() {
  var KEY = 'ntumc-lang';
  var saved = localStorage.getItem(KEY);
  if (saved) {
    var tab = document.getElementById('tab-' + saved);
    if (tab) new bootstrap.Tab(tab).show();
  }
  document.querySelectorAll('[data-bs-toggle="tab"]').forEach(function(btn) {
    btn.addEventListener('shown.bs.tab', function() {
      var lang = btn.id.replace('tab-', '');
      localStorage.setItem(KEY, lang);
    });
  });
})();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Spacing calculation
# ---------------------------------------------------------------------------


def compute_nospace(words: list[dict], sent_text: str) -> list[bool]:
    """Compute nospace flag for each word (True = no space before next word).

    Uses cfrom/cto offsets when present; falls back to scanning sent_text.
    The last word always returns False.

    Args:
        words: List of word dicts with at least 'word', and optionally 'cfrom'/'cto'.
        sent_text: The full sentence text.

    Returns:
        List of bool, same length as words.
    """
    n = len(words)
    if n == 0:
        return []

    # Try cfrom/cto first
    if n > 1 and words[0].get("cfrom") is not None and words[1].get("cfrom") is not None:
        result = []
        for i, w in enumerate(words):
            if i < n - 1 and w.get("cto") is not None and words[i + 1].get("cfrom") is not None:
                result.append(int(w["cto"]) == int(words[i + 1]["cfrom"]))
            else:
                result.append(False)
        return result

    # Fall back: scan sentence text
    result = [False] * n
    pos = 0
    for i, w in enumerate(words[:-1]):
        surface = w["word"]
        idx = sent_text.find(surface, pos)
        if idx == -1:
            continue
        end = idx + len(surface)
        pos = end
        next_surface = words[i + 1]["word"]
        next_idx = sent_text.find(next_surface, pos)
        if next_idx == pos:
            result[i] = True

    return result


# ---------------------------------------------------------------------------
# Data extraction
# ---------------------------------------------------------------------------


def build_concept_info(doc_data: dict) -> dict:
    """Extract concept info and annotate each sentence with word_cids.

    Mutates each sentence dict in doc_data to add:
      - ``word_cids``: {wid: [concept_key, ...]}

    Also annotates each word dict with ``nospace`` bool.

    Returns:
        concepts: {concept_key: {l, s, w}} using compact keys.
    """
    concepts: dict = {}

    for sent in doc_data["sentences"]:
        sid = sent["sid"]
        sent_text = sent.get("text", "")
        words = sent.get("words", [])
        word_cids: dict[int, list[str]] = {}

        for concept in sent.get("concepts", []):
            tag = concept.get("tag") or ""
            if not tag or tag in SKIP_TAGS:
                continue

            cid = concept["cid"]
            key = f"c{sid}:{cid}"
            wids: list[int] = concept.get("wids", [])

            concepts[key] = {
                "l": concept.get("clemma", ""),
                "s": tag,
                "w": wids,
            }

            for wid in wids:
                word_cids.setdefault(wid, []).append(key)

        sent["word_cids"] = word_cids

        # Compute spacing and annotate words
        nospace_flags = compute_nospace(words, sent_text)
        for word, ns in zip(words, nospace_flags):
            word["nospace"] = ns

    return concepts


def get_doc_tagging_rates(corpus_db: str) -> dict[int, float]:
    """Return word-level tagging rates (0–1) for every document.

    A word is "tagged" if it appears in cwl linked to a concept with a
    valid (non-skip) tag.

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
                COUNT(DISTINCT w.sid || ':' || CAST(w.wid AS TEXT)) AS total,
                COUNT(DISTINCT CASE
                    WHEN c.tag IS NOT NULL AND c.tag != ''
                         AND c.tag NOT IN ('x','w','e')
                    THEN cwl.sid || ':' || CAST(cwl.wid AS TEXT)
                END) AS tagged
            FROM sent s
            JOIN word w ON w.sid = s.sid
            LEFT JOIN cwl ON cwl.sid = w.sid AND cwl.wid = w.wid
            LEFT JOIN concept c ON c.sid = cwl.sid AND c.cid = cwl.cid
            GROUP BY s.docID
            """
        ).fetchall()
        return {
            docid: (tagged / total if total > 0 else 0.0)
            for docid, total, tagged in rows
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------


def render_html(
    doc_data: dict,
    concepts: dict,
    lang: str,
    assets_path: str,
    index_path: str,
) -> str:
    """Render the document HTML page with concept data embedded inline.

    Synset definitions, synonyms, and translations are loaded dynamically
    from shared JSON data files.

    Args:
        doc_data: Document dict (sentences annotated with word_cids and nospace).
        concepts: Concepts dict to embed as JavaScript.
        lang: Language code of the document.
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
        concepts_data=Markup(json.dumps(concepts, ensure_ascii=False)),
        doc_lang_json=Markup(json.dumps(lang)),
        data_path_json=Markup(json.dumps("../data")),
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
    """Generate the HTML display file for one document.

    Args:
        corpus_db: Path to the language corpus database.
        docid: Document ID to process.
        outdir: Root output directory (e.g. display/).
        lang: Language code (e.g. 'eng').
        tag_rate: Pre-computed tagging rate (0–1), used for index display.

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
    tag_pct = f"{tag_rate * 100:.0f}" if tag_rate is not None else ""
    logger.info(
        "Processing '%s' (%d sentences%s)...",
        title,
        n_sents,
        f", {tag_pct}% tagged" if tag_pct else "",
    )

    concepts = build_concept_info(doc_data)

    lang_dir = outdir / lang
    lang_dir.mkdir(parents=True, exist_ok=True)
    html_path = lang_dir / f"{doc_name}-view.html"

    html = render_html(
        doc_data,
        concepts=concepts,
        lang=lang,
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
        "tag_pct": tag_pct,
        "corpus_id": doc_data.get("corpusID"),
    }


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

    env = Environment(loader=BaseLoader(), autoescape=True)
    tmpl = env.from_string(INDEX_TEMPLATE)
    html = tmpl.render(by_lang=by_lang, lang_names=lang_names)
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
        sid_list = sorted(sids)
        ph = ",".join("?" * len(sid_list))
        rows = conn.execute(
            f"SELECT sid, sent FROM sent WHERE sid IN ({ph})", sid_list
        ).fetchall()
        conn.close()
        sent_data = {str(r[0]): r[1] for r in rows}
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

    corpus_db = args.corpus_db or str(BUILD_DIR / f"{args.lang}.db")

    if not Path(corpus_db).exists():
        logger.error("Database not found: %s", corpus_db)
        sys.exit(1)

    corpus = Corpus(corpus_db)

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
        docid = corpus.get_docid_by_docname(args.doc)
        if docid is None:
            logger.error("Document '%s' not found in %s", args.doc, corpus_db)
            sys.exit(1)
        docids = [docid]
    else:
        docids = [args.docid]

    lang_docs: list[dict] = []

    for docid in docids:
        meta = write_document(
            corpus_db, docid, outdir, args.lang,
            tag_rate=tag_rates.get(docid),
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
