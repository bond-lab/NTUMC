#!/usr/bin/env python3
"""Recover missing standalone concept annotations into cmn.db from older DBs.

Imports concepts that exist in an older cmn.db but are completely absent
from the current build — i.e., none of the concept's words are annotated
by any other concept in the build.  Skips MWE-overlap cases where the
build already annotates the same words differently.

Usage:
    .venv/bin/python scripts/recover_cmn_concepts.py --dry-run
    .venv/bin/python scripts/recover_cmn_concepts.py --fix
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
CMN_DB = BUILD_DIR / "cmn.db"
OLD_CMN_DB = Path.home() / "work" / "ntu-mc" / "2016-11-30" / "cmn.db"

SKIP_TAGS: frozenset[str] = frozenset({"x", "w", "e"})


def _find_wids_for_clemma(
    words: list[tuple[int, str, str]],
    clemma: str,
) -> list[int]:
    """Find wids in a word list whose forms match the clemma.

    Args:
        words: [(wid, word, lemma), ...] for one sentence.
        clemma: Concept lemma (may have underscores for MWE parts).

    Returns:
        List of matching wids, or empty if no match found.
    """
    parts = [p for p in re.split(r'[_ ]+', clemma) if p]
    if not parts:
        return []

    n = len(parts)
    for i in range(len(words) - n + 1):
        window = words[i:i + n]
        if all(
            p.lower() in w.lower() or p.lower() in l.lower()
            for p, (_, w, l) in zip(parts, window)
        ):
            return [w[0] for w in window]

    if n == 1:
        target = parts[0].lower()
        for wid, word, lemma in words:
            if word.lower() == target or lemma.lower() == target:
                return [wid]

    return []


def load_build_tagged_wids(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """Load all (sid, wid) pairs that have a tagged concept in the build.

    Returns:
        {sid: {wid, ...}} for words linked to any non-skip-tagged concept.
    """
    rows = conn.execute(
        "SELECT cw.sid, cw.wid FROM cwl cw "
        "JOIN concept c ON c.sid = cw.sid AND c.cid = cw.cid "
        "WHERE c.tag IS NOT NULL AND c.tag != '' "
        "AND c.tag NOT IN ('x', 'w', 'e')"
    ).fetchall()
    result: dict[int, set[int]] = {}
    for sid, wid in rows:
        result.setdefault(sid, set()).add(wid)
    return result


def load_build_concepts(conn: sqlite3.Connection) -> set[tuple[int, int]]:
    """Load all (sid, cid) pairs from the build concept table.

    Returns:
        Set of (sid, cid) for all concepts (tagged or not).
    """
    rows = conn.execute("SELECT sid, cid FROM concept").fetchall()
    return {(r[0], r[1]) for r in rows}


def find_standalone_missing(
    old_conn: sqlite3.Connection,
    build_concepts: set[tuple[int, int]],
    build_tagged_wids: dict[int, set[int]],
    sid_min: int,
    sid_max: int,
) -> list[dict]:
    """Find concepts in old DB that are standalone-missing from the build.

    A concept is standalone-missing if:
      1. Its (sid, cid) is not in the build concept table
      2. It has a valid (non-skip) tag
      3. None of its wids are tagged by any other concept in the build

    Args:
        old_conn: Connection to the old cmn.db.
        build_concepts: All (sid, cid) in the build.
        build_tagged_wids: {sid: {tagged wids}} in the build.
        sid_min: Start of sid range.
        sid_max: End of sid range.

    Returns:
        List of dicts with keys: sid, cid, clemma, tag, comment, wids.
    """
    old_concepts = old_conn.execute(
        "SELECT sid, cid, clemma, tag, comment FROM concept "
        "WHERE sid BETWEEN ? AND ? "
        "AND tag IS NOT NULL AND tag != '' AND tag NOT IN ('x', 'w', 'e')",
        (sid_min, sid_max),
    ).fetchall()

    old_cwl: dict[tuple[int, int], list[int]] = {}
    for r in old_conn.execute(
        "SELECT sid, cid, wid FROM cwl WHERE sid BETWEEN ? AND ?",
        (sid_min, sid_max),
    ).fetchall():
        old_cwl.setdefault((r[0], r[1]), []).append(r[2])

    results = []
    for sid, cid, clemma, tag, comment in old_concepts:
        if (sid, cid) in build_concepts:
            continue

        wids = old_cwl.get((sid, cid), [])
        if not wids:
            continue

        build_wids_for_sid = build_tagged_wids.get(sid, set())
        if any(w in build_wids_for_sid for w in wids):
            continue

        results.append({
            "sid": sid, "cid": cid, "clemma": clemma,
            "tag": tag, "comment": comment, "wids": wids,
        })

    return results


def import_concepts(
    build_conn: sqlite3.Connection,
    concepts: list[dict],
    dry_run: bool,
) -> int:
    """Insert standalone-missing concepts and their cwl links into the build.

    Args:
        build_conn: Connection to the build cmn.db.
        concepts: List of concept dicts from find_standalone_missing.
        dry_run: If True, count but don't insert.

    Returns:
        Number of concepts imported.
    """
    if not concepts:
        return 0

    if dry_run:
        return len(concepts)

    valid_words = {
        (r[0], r[1])
        for r in build_conn.execute("SELECT sid, wid FROM word").fetchall()
    }

    words_by_sid: dict[int, list[tuple[int, str, str]]] = {}
    for sid, wid, word, lemma in build_conn.execute(
        "SELECT sid, wid, word, lemma FROM word ORDER BY sid, wid"
    ).fetchall():
        words_by_sid.setdefault(sid, []).append((wid, word, lemma))

    imported = 0
    skipped = 0
    remapped = 0
    for c in concepts:
        good_wids = [w for w in c["wids"] if (c["sid"], w) in valid_words]
        if not good_wids:
            good_wids = _find_wids_for_clemma(
                words_by_sid.get(c["sid"], []), c["clemma"],
            )
            if good_wids:
                remapped += 1
            else:
                skipped += 1
                continue

        build_conn.execute(
            "INSERT OR IGNORE INTO concept (sid, cid, clemma, tag, comment) "
            "VALUES (?, ?, ?, ?, ?)",
            (c["sid"], c["cid"], c["clemma"], c["tag"], c["comment"]),
        )
        for wid in good_wids:
            build_conn.execute(
                "INSERT OR IGNORE INTO cwl (sid, wid, cid) VALUES (?, ?, ?)",
                (c["sid"], wid, c["cid"]),
            )
        imported += 1

    if skipped:
        logger.warning("Skipped %d concepts with no matching words in build", skipped)
    if remapped:
        logger.info("Remapped %d concepts to new wids by clemma matching", remapped)

    build_conn.commit()
    return imported


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Recover missing standalone concept annotations into cmn.db."
    )
    parser.add_argument("--fix", action="store_true", help="Apply imports")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    if not CMN_DB.exists():
        logger.error("Build cmn.db not found: %s", CMN_DB)
        sys.exit(1)
    if not OLD_CMN_DB.exists():
        logger.error("Old cmn.db not found: %s", OLD_CMN_DB)
        sys.exit(1)

    build_conn = sqlite3.connect(str(CMN_DB))
    old_conn = sqlite3.connect(str(OLD_CMN_DB))

    # Disable triggers to avoid log table issues
    triggers = build_conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
    ).fetchall()
    if triggers and not args.dry_run:
        logger.info("Temporarily dropping %d triggers...", len(triggers))
        for name, _ in triggers:
            build_conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        build_conn.commit()

    logger.info("Loading build state...")
    build_concepts = load_build_concepts(build_conn)
    build_tagged_wids = load_build_tagged_wids(build_conn)
    logger.info(
        "  %d concepts, %d sids with tagged words",
        len(build_concepts), len(build_tagged_wids),
    )

    # Get doc ranges from build
    doc_ranges = build_conn.execute(
        "SELECT d.doc, MIN(s.sid), MAX(s.sid) "
        "FROM sent s JOIN doc d ON s.docID = d.docid "
        "GROUP BY d.doc ORDER BY MIN(s.sid)"
    ).fetchall()

    total_imported = 0
    action = "would import" if args.dry_run else "importing"

    for doc, smin, smax in doc_ranges:
        missing = find_standalone_missing(
            old_conn, build_concepts, build_tagged_wids, smin, smax,
        )
        if not missing:
            continue

        n_wids = sum(len(c["wids"]) for c in missing)
        logger.info(
            "  %s: %s %d concepts (%d cwl links)",
            doc, action, len(missing), n_wids,
        )
        total_imported += import_concepts(build_conn, missing, args.dry_run)

    # Restore triggers
    if triggers and not args.dry_run:
        logger.info("Restoring %d triggers...", len(triggers))
        for _, sql in triggers:
            if sql:
                build_conn.execute(sql)
        build_conn.commit()

    old_conn.close()
    build_conn.close()

    logger.info("Total: %s %d concepts", action, total_imported)


if __name__ == "__main__":
    main()
