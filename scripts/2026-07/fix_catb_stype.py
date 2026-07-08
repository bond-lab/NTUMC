#!/usr/bin/env python3
"""Fix stype annotations for The Cathedral and the Bazaar (catb).

Downloads the original essay from catb.org, extracts paragraph boundaries
from its HTML structure, and sets stype in eng.db accordingly:

  - h1: document title (sid 1)
  - h2: section headings (Abstract, section titles)
  - author: author line (sid 2)
  - item: numbered lessons/aphorisms (e.g. "1. Every good work...")
  - p: first sentence of each paragraph
  - (no stype): continuation sentences within a paragraph

Then propagates to other languages via propagate_stype.py's logic.

Usage:
    .venv/bin/python scripts/fix_catb_stype.py --dry-run
    .venv/bin/python scripts/fix_catb_stype.py --fix
"""

import argparse
import logging
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"

BASE_URL = "https://www.catb.org/~esr/writings/cathedral-bazaar/cathedral-bazaar/"
SECTION_PAGES = [
    "",
    "ar01s02.html",
    "ar01s03.html",
    "ar01s04.html",
    "ar01s05.html",
    "ar01s06.html",
    "ar01s07.html",
    "ar01s08.html",
    "ar01s09.html",
    "ar01s10.html",
    "ar01s11.html",
    "ar01s12.html",
    "ar01s13.html",
    "ar01s14.html",
    "ar01s15.html",
    "ar01s16.html",
]

SECTION_HEADINGS = {
    "The Cathedral and the Bazaar",
    "The Mail Must Get Through",
    "The Importance of Having Users",
    "Release Early, Release Often",
    "How Many Eyeballs Tame Complexity",
    "When Is a Rose Not a Rose?",
    "Popclient becomes Fetchmail",
    "Fetchmail Grows Up",
    "A Few More Lessons from Fetchmail",
    "Necessary Preconditions for the Bazaar Style",
    "The Social Context of Open-Source Software",
    "On Management and the Maginot Line",
    "Epilog: Netscape Embraces the Bazaar",
    "Notes",
    "Bibliography",
    "Acknowledgements",
    "Abstract",
}


def download_essay() -> list[list[str]]:
    """Download the essay HTML and extract paragraphs.

    Returns:
        List of paragraphs, each a list of sentences (first ~8 words
        of each sentence, normalised for matching).
    """
    paragraphs: list[str] = []

    for page in SECTION_PAGES:
        url = BASE_URL + page
        result = subprocess.run(
            ["curl", "-k", "-s", url],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Failed to fetch %s", url)
            continue

        html = result.stdout.decode("iso-8859-1")
        raw_paras = re.findall(
            r'<p\b[^>]*>(.*?)</p>', html, re.DOTALL,
        )
        for raw in raw_paras:
            text = re.sub(r'<[^>]+>', '', raw)
            text = re.sub(r'\s+', ' ', text).strip()
            if len(text) > 20:
                paragraphs.append(text)

    logger.info("Downloaded %d paragraphs from %s", len(paragraphs), BASE_URL)
    return paragraphs


def normalise(text: str) -> str:
    """Normalise text for fuzzy matching."""
    text = re.sub(r'[``“”"‘’\']', '', text)
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s]', '', text)
    return text.lower().strip()


def first_n_words(text: str, n: int = 6) -> str:
    """Return first n words of normalised text."""
    return ' '.join(normalise(text).split()[:n])


def find_paragraph_starts(
    paragraphs: list[str],
    sentences: list[tuple[int, str]],
) -> set[int]:
    """Match downloaded paragraphs to sentence IDs.

    Args:
        paragraphs: Downloaded paragraph texts.
        sentences: (sid, sent_text) from the database.

    Returns:
        Set of sids that start a paragraph.
    """
    para_keys = set()
    for p in paragraphs:
        key = first_n_words(p)
        if key:
            para_keys.add(key)

    para_starts = set()
    for sid, sent in sentences:
        key = first_n_words(sent)
        if key in para_keys:
            para_starts.add(sid)

    return para_starts


def compute_catb_stypes(
    conn: sqlite3.Connection,
    para_starts: set[int],
) -> list[tuple[int, str]]:
    """Compute the correct stype for each catb sentence.

    Args:
        conn: Connection to eng.db.
        para_starts: Set of sids that begin a paragraph.

    Returns:
        List of (sid, stype) for sentences that should have stype.
        Sentences not in the list should have no stype row.
    """
    rows = conn.execute(
        "SELECT sid, sent FROM sent WHERE docID = 502 ORDER BY sid"
    ).fetchall()

    stypes: list[tuple[int, str]] = []

    for sid, sent in rows:
        stripped = sent.strip()

        if sid == 1:
            stypes.append((sid, "h1"))
        elif sid == 2:
            stypes.append((sid, "author"))
        elif sid == 12 or stripped in SECTION_HEADINGS:
            stypes.append((sid, "h2"))
        elif re.match(r'^\d+[\.:]\s', stripped):
            stypes.append((sid, "item"))
        elif sid in para_starts:
            stypes.append((sid, "p"))

    return stypes


def apply_stypes(
    conn: sqlite3.Connection,
    stypes: list[tuple[int, str]],
    dry_run: bool,
) -> int:
    """Replace all catb stype entries with the corrected set.

    Args:
        conn: Connection to eng.db.
        stypes: New (sid, stype) pairs.
        dry_run: If True, report but don't modify.

    Returns:
        Number of changes.
    """
    old_count = conn.execute(
        "SELECT count(*) FROM stype WHERE sid BETWEEN 1 AND 769"
    ).fetchone()[0]

    by_type: dict[str, int] = {}
    for _, stype in stypes:
        by_type[stype] = by_type.get(stype, 0) + 1

    logger.info(
        "catb stypes: %d old → %d new %s",
        old_count, len(stypes), dict(sorted(by_type.items())),
    )

    if dry_run:
        return len(stypes)

    conn.execute("DELETE FROM stype WHERE sid BETWEEN 1 AND 769")
    conn.executemany(
        "INSERT INTO stype (sid, stype) VALUES (?, ?)", stypes,
    )
    conn.commit()
    logger.info("eng.db: replaced %d → %d stype entries for catb", old_count, len(stypes))
    return len(stypes)


def propagate_to_other_langs(dry_run: bool) -> None:
    """Re-propagate catb stypes to other languages.

    Clears existing catb stypes in target languages and re-runs
    propagation from eng via slinks.
    """
    from propagate_stype import load_eng_stypes, load_slinks, load_valid_sids

    eng_stypes = load_eng_stypes()
    catb_eng_sids = set(range(1, 770))
    catb_stypes = {
        sid: stype for sid, stype in eng_stypes.items() if sid in catb_eng_sids
    }

    for lang in ["jpn", "cmn"]:
        db_path = BUILD_DIR / f"{lang}.db"
        if not db_path.exists():
            continue

        slinks = load_slinks(lang)
        if not slinks:
            logger.info("  %s: no slinks, skipping", lang)
            continue

        catb_tgt_sids: set[int] = set()
        for eng_sid in catb_eng_sids:
            tgt_sids = slinks.get(eng_sid, [])
            catb_tgt_sids.update(tgt_sids)

        if not catb_tgt_sids:
            continue

        conn = sqlite3.connect(str(db_path))
        valid_sids = {
            r[0] for r in conn.execute("SELECT sid FROM sent").fetchall()
        }
        existing = {
            r[0] for r in conn.execute("SELECT sid FROM stype").fetchall()
        }

        old_catb = conn.execute(
            "SELECT count(*) FROM stype WHERE sid IN ({})".format(
                ",".join("?" * len(catb_tgt_sids))
            ),
            list(catb_tgt_sids),
        ).fetchone()[0]

        new_stypes: dict[int, str] = {}
        for eng_sid, stype in catb_stypes.items():
            tgt_sids = slinks.get(eng_sid)
            if not tgt_sids:
                continue
            first_tgt = tgt_sids[0]
            if first_tgt in valid_sids:
                new_stypes[first_tgt] = stype

        by_type: dict[str, int] = {}
        for stype in new_stypes.values():
            by_type[stype] = by_type.get(stype, 0) + 1

        logger.info(
            "  %s: %d old → %d new %s",
            lang, old_catb, len(new_stypes), dict(sorted(by_type.items())),
        )

        if not dry_run:
            ph = ",".join("?" * len(catb_tgt_sids))
            conn.execute(
                f"DELETE FROM stype WHERE sid IN ({ph})", list(catb_tgt_sids),
            )
            conn.executemany(
                "INSERT INTO stype (sid, stype) VALUES (?, ?)",
                list(new_stypes.items()),
            )
            conn.commit()
            logger.info("  %s: updated", lang)

        conn.close()


def handle_item_continuations(
    conn: sqlite3.Connection,
    stypes: list[tuple[int, str]],
) -> list[tuple[int, str]]:
    """Add item stype for continuation lines of multi-sentence lessons.

    Lessons 2 (sids 64-65) and 7 (sids 156-158) span multiple sentences.
    The numbered first line is already tagged; this adds the continuations.

    Args:
        conn: Connection to eng.db.
        stypes: Current stype list.

    Returns:
        Updated stype list with continuations added.
    """
    existing_sids = {sid for sid, _ in stypes}
    rows = conn.execute(
        "SELECT sid, sent FROM sent WHERE docID = 502 ORDER BY sid"
    ).fetchall()

    continuations = {
        65: "Great ones know what to rewrite",
        157: "Release often.",
        158: "And listen to your customers.",
    }

    for sid, sent in rows:
        if sid in continuations and sid not in existing_sids:
            if sent.strip().startswith(continuations[sid][:20]):
                stypes.append((sid, "item"))

    return stypes


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Fix stype annotations for The Cathedral and the Bazaar."
    )
    parser.add_argument("--fix", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    eng_db = BUILD_DIR / "eng.db"
    if not eng_db.exists():
        logger.error("eng.db not found: %s", eng_db)
        sys.exit(1)

    paragraphs = download_essay()

    conn = sqlite3.connect(str(eng_db))
    sentences = conn.execute(
        "SELECT sid, sent FROM sent WHERE docID = 502 ORDER BY sid"
    ).fetchall()

    para_starts = find_paragraph_starts(paragraphs, sentences)
    logger.info("Matched %d paragraph starts", len(para_starts))

    stypes = compute_catb_stypes(conn, para_starts)
    stypes = handle_item_continuations(conn, stypes)

    n = apply_stypes(conn, stypes, dry_run=args.dry_run)
    conn.close()

    logger.info("Propagating to other languages...")
    propagate_to_other_langs(dry_run=args.dry_run)

    action = "would apply" if args.dry_run else "applied"
    logger.info("Done. %s %d eng stypes + propagated to jpn/cmn.", action, n)


if __name__ == "__main__":
    main()
