#!/usr/bin/env python3
"""Propagate stype (sentence type) annotations from English to other languages.

Stype values (p, h0, h1, ...) indicate paragraph boundaries and headings.
These are structural and transfer across languages.  This script propagates
stypes from eng.db to jpn/cmn/ind/ita/ces using:

  1. Sentence links (slinks) for story/essay docs — for 1:many links,
     only the first target sid gets the stype.
  2. Direct sid matching for tourism docs (sid >= 100000) which share
     sid ranges across languages.

Only inserts stypes where the target has no existing stype.

Usage:
    .venv/bin/python scripts/propagate_stype.py --dry-run
    .venv/bin/python scripts/propagate_stype.py --fix
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"

TARGET_LANGS = ["jpn", "cmn", "ind", "ita", "ces"]


def load_eng_stypes() -> dict[int, str]:
    """Load all non-empty stypes from eng.db.

    Returns:
        {sid: stype}
    """
    conn = sqlite3.connect(str(BUILD_DIR / "eng.db"))
    rows = conn.execute(
        "SELECT sid, stype FROM stype WHERE stype IS NOT NULL AND stype != ''"
    ).fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def load_slinks(lang: str) -> dict[int, list[int]]:
    """Load eng→lang slinks, trying both filename orderings.

    Returns:
        {eng_sid: [target_sids sorted]}
    """
    candidates = [f"eng-{lang}.db", f"{lang}-eng.db"]
    for name in candidates:
        db_path = BUILD_DIR / name
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path))
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "slink" not in tables:
            conn.close()
            continue
        first_lang = name.split("-")[0]

        if first_lang == "eng":
            rows = conn.execute(
                "SELECT fsid, tsid FROM slink ORDER BY fsid, tsid"
            ).fetchall()
            result: dict[int, list[int]] = {}
            for fsid, tsid in rows:
                result.setdefault(fsid, []).append(tsid)
        else:
            rows = conn.execute(
                "SELECT fsid, tsid FROM slink ORDER BY tsid, fsid"
            ).fetchall()
            result = {}
            for fsid, tsid in rows:
                result.setdefault(tsid, []).append(fsid)

        conn.close()
        return result

    return {}


def load_existing_stypes(lang: str) -> set[int]:
    """Load sids that already have an stype in the target language.

    Returns:
        Set of sids with existing stypes.
    """
    conn = sqlite3.connect(str(BUILD_DIR / f"{lang}.db"))
    rows = conn.execute("SELECT sid FROM stype").fetchall()
    conn.close()
    return {r[0] for r in rows}


def load_valid_sids(lang: str) -> set[int]:
    """Load all sids that exist in the target language sent table.

    Returns:
        Set of valid sids.
    """
    conn = sqlite3.connect(str(BUILD_DIR / f"{lang}.db"))
    rows = conn.execute("SELECT sid FROM sent").fetchall()
    conn.close()
    return {r[0] for r in rows}


def propagate_to_lang(
    lang: str,
    eng_stypes: dict[int, str],
    dry_run: bool,
) -> int:
    """Propagate stypes from English to one target language.

    Args:
        lang: Target language code.
        eng_stypes: {eng_sid: stype} from English.
        dry_run: If True, count but don't insert.

    Returns:
        Number of stypes propagated.
    """
    db_path = BUILD_DIR / f"{lang}.db"
    if not db_path.exists():
        logger.warning("  %s.db not found, skipping", lang)
        return 0

    existing = load_existing_stypes(lang)
    valid_sids = load_valid_sids(lang)
    slinks = load_slinks(lang)

    new_stypes: dict[int, str] = {}

    for eng_sid, stype in eng_stypes.items():
        if eng_sid >= 100000:
            # Tourism docs: direct sid mapping
            if eng_sid in valid_sids and eng_sid not in existing:
                new_stypes[eng_sid] = stype
        elif slinks:
            # Story/essay docs: use slinks
            tgt_sids = slinks.get(eng_sid)
            if not tgt_sids:
                continue
            first_tgt = tgt_sids[0]
            if first_tgt not in existing:
                new_stypes[first_tgt] = stype

    if not new_stypes:
        logger.info("  %s: nothing to propagate", lang)
        return 0

    action = "would insert" if dry_run else "inserting"
    by_type: dict[str, int] = {}
    for stype in new_stypes.values():
        by_type[stype] = by_type.get(stype, 0) + 1
    logger.info(
        "  %s: %s %d stypes %s",
        lang, action, len(new_stypes), dict(sorted(by_type.items())),
    )

    if not dry_run:
        conn = sqlite3.connect(str(db_path))
        conn.executemany(
            "INSERT OR IGNORE INTO stype (sid, stype) VALUES (?, ?)",
            list(new_stypes.items()),
        )
        conn.commit()
        conn.close()

    return len(new_stypes)


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Propagate stype annotations from English to other languages."
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

    eng_stypes = load_eng_stypes()
    logger.info("Loaded %d English stypes", len(eng_stypes))

    total = 0
    for lang in TARGET_LANGS:
        total += propagate_to_lang(lang, eng_stypes, dry_run=args.dry_run)

    action = "would propagate" if args.dry_run else "propagated"
    logger.info("Total: %s %d stypes", action, total)


if __name__ == "__main__":
    main()
