#!/usr/bin/env python3
"""Fix off-by-one-sentence errors in concept-word links.

Finds concepts whose clemma doesn't match their linked words but does
match words in an adjacent sentence (sid±1).  Two cases:

1. **Duplicate**: the adjacent sentence already has a concept with the
   same clemma → delete the misplaced concept and its cwl rows.

2. **Move**: the adjacent sentence has no matching concept → re-point
   the concept and cwl rows to the correct sentence and wids.

Checks both multi-word and single-word concepts.

Usage:
    .venv/bin/python scripts/fix_cwl_offbyone.py --dry-run
    .venv/bin/python scripts/fix_cwl_offbyone.py --dry-run --lang cmn
    .venv/bin/python scripts/fix_cwl_offbyone.py --fix
"""

import argparse
import logging
import re
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parents[2] / "build"
ALL_LANGS = ["eng", "cmn", "jpn", "ind", "ita", "ces"]
SKIP_TAGS = {"e", "u", "m", "h", "s", "x", "w", "org", "per", "dat", "oth", "num", ""}


def normalise(text: str) -> str:
    """Remove underscores and spaces, lowercase."""
    return text.replace("_", "").replace(" ", "").lower()


def find_wids_for_clemma(
    conn: sqlite3.Connection,
    target_sid: int,
    clemma: str,
) -> list[int]:
    """Find the wids in target_sid whose words match the clemma parts.

    Args:
        conn: Database connection.
        target_sid: Sentence to search in.
        clemma: Concept lemma (may contain underscores for MWE parts).

    Returns:
        List of matching wids (contiguous), or empty if no clean match.
    """
    words = conn.execute(
        "SELECT wid, word, lemma FROM word WHERE sid = ? ORDER BY wid",
        (target_sid,),
    ).fetchall()

    parts = [p for p in re.split(r'[_ ]+', clemma) if p]
    if not parts:
        return []

    norm_parts = [p.lower() for p in parts]
    n = len(norm_parts)

    for i in range(len(words) - n + 1):
        window = words[i:i + n]
        w_words = [w[1].lower() for w in window]
        w_lemmas = [w[2].lower() for w in window]

        if all(p in wd or p in wl for p, wd, wl in zip(norm_parts, w_words, w_lemmas)):
            return [w[0] for w in window]

    for i in range(len(words)):
        if (words[i][1].lower() == normalise(clemma)
                or words[i][2].lower() == normalise(clemma)):
            return [words[i][0]]

    return []


def find_misplaced_concepts(conn: sqlite3.Connection) -> list[dict]:
    """Find concepts whose clemma doesn't match their words but matches sid±1.

    Args:
        conn: Database connection.

    Returns:
        List of finding dicts with keys: sid, cid, clemma, tag, offset,
        target_sid, action ('delete' or 'move'), target_wids.
    """
    rows = conn.execute("""
        SELECT c.sid, c.cid, c.clemma, c.tag,
               GROUP_CONCAT(w.word, '') AS word_concat,
               GROUP_CONCAT(w.lemma, '') AS lemma_concat,
               COUNT(cwl.wid) AS n_words
        FROM concept c
        JOIN cwl ON cwl.sid = c.sid AND cwl.cid = c.cid
        JOIN word w ON w.sid = cwl.sid AND w.wid = cwl.wid
        WHERE c.tag NOT IN ({})
        GROUP BY c.sid, c.cid
    """.format(",".join("?" * len(SKIP_TAGS))), list(SKIP_TAGS)).fetchall()

    findings = []
    for sid, cid, clemma, tag, word_concat, lemma_concat, n_words in rows:
        nc = normalise(clemma)

        if nc == normalise(word_concat) or nc == normalise(lemma_concat):
            continue
        if nc in normalise(word_concat) or normalise(word_concat) in nc:
            continue
        if nc in normalise(lemma_concat) or normalise(lemma_concat) in nc:
            continue

        for offset in [1, -1]:
            target_sid = sid + offset
            target_words = conn.execute(
                "SELECT GROUP_CONCAT(word, '') FROM word WHERE sid = ? ORDER BY wid",
                (target_sid,),
            ).fetchone()
            if not (target_words and target_words[0]):
                continue
            if nc not in target_words[0].lower():
                target_lemmas = conn.execute(
                    "SELECT GROUP_CONCAT(lemma, '') FROM word WHERE sid = ? ORDER BY wid",
                    (target_sid,),
                ).fetchone()
                if not (target_lemmas and target_lemmas[0] and nc in target_lemmas[0].lower()):
                    continue

            existing = conn.execute(
                "SELECT cid FROM concept WHERE sid = ? "
                "AND LOWER(REPLACE(REPLACE(clemma, '_', ''), ' ', '')) = ?",
                (target_sid, nc),
            ).fetchone()

            if existing:
                action = "delete"
                target_wids = []
            else:
                target_wids = find_wids_for_clemma(conn, target_sid, clemma)
                if not target_wids:
                    continue
                action = "move"

            findings.append({
                "sid": sid,
                "cid": cid,
                "clemma": clemma,
                "tag": tag,
                "offset": offset,
                "target_sid": target_sid,
                "action": action,
                "target_wids": target_wids,
            })
            break

    return findings


def apply_fixes(
    conn: sqlite3.Connection,
    findings: list[dict],
    lang: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Apply fixes for misplaced concepts.

    Args:
        conn: Database connection.
        findings: From find_misplaced_concepts.
        lang: Language code (for logging).
        dry_run: If True, report but don't modify.

    Returns:
        (n_deleted, n_moved) tuple.
    """
    n_deleted = 0
    n_moved = 0

    if not dry_run:
        triggers = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        for name, _ in triggers:
            conn.execute(f"DROP TRIGGER [{name}]")

    for f in findings:
        sid, cid = f["sid"], f["cid"]
        action = f["action"]

        if action == "delete":
            if not dry_run:
                conn.execute(
                    "DELETE FROM cwl WHERE sid = ? AND cid = ?", (sid, cid),
                )
                conn.execute(
                    "DELETE FROM concept WHERE sid = ? AND cid = ?", (sid, cid),
                )
            n_deleted += 1

        elif action == "move":
            target_sid = f["target_sid"]
            target_wids = f["target_wids"]

            new_cid = conn.execute(
                "SELECT COALESCE(MAX(cid), -1) + 1 FROM concept WHERE sid = ?",
                (target_sid,),
            ).fetchone()[0]

            concept_row = conn.execute(
                "SELECT clemma, tag, comment, usrname "
                "FROM concept WHERE sid = ? AND cid = ?",
                (sid, cid),
            ).fetchone()
            if not concept_row:
                continue

            if not dry_run:
                conn.execute(
                    "DELETE FROM cwl WHERE sid = ? AND cid = ?", (sid, cid),
                )
                conn.execute(
                    "DELETE FROM concept WHERE sid = ? AND cid = ?", (sid, cid),
                )
                conn.execute(
                    "INSERT INTO concept (sid, cid, clemma, tag, comment, usrname) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (target_sid, new_cid, concept_row[0], concept_row[1],
                     concept_row[2], concept_row[3]),
                )
                for wid in target_wids:
                    conn.execute(
                        "INSERT OR IGNORE INTO cwl (sid, wid, cid) VALUES (?, ?, ?)",
                        (target_sid, wid, new_cid),
                    )
            n_moved += 1

    if not dry_run:
        for _, sql in triggers:
            if sql:
                conn.executescript(sql)

    return n_deleted, n_moved


def verify_fixes(conn: sqlite3.Connection, findings: list[dict]) -> list[str]:
    """Sanity-check the proposed fixes before applying.

    Args:
        conn: Database connection.
        findings: From find_misplaced_concepts.

    Returns:
        List of warning strings (empty = all OK).
    """
    warnings = []

    for f in findings:
        sid, cid = f["sid"], f["cid"]

        concept = conn.execute(
            "SELECT clemma, tag FROM concept WHERE sid = ? AND cid = ?",
            (sid, cid),
        ).fetchone()
        if not concept:
            warnings.append(f"sid={sid} cid={cid}: concept row not found")
            continue

        cwl_rows = conn.execute(
            "SELECT wid FROM cwl WHERE sid = ? AND cid = ?", (sid, cid),
        ).fetchall()
        if not cwl_rows:
            warnings.append(f"sid={sid} cid={cid}: no cwl rows found")

        same_doc = conn.execute(
            "SELECT s1.docID = s2.docID FROM sent s1, sent s2 "
            "WHERE s1.sid = ? AND s2.sid = ?",
            (sid, f["target_sid"]),
        ).fetchone()
        if not same_doc or not same_doc[0]:
            warnings.append(
                f"sid={sid} cid={cid}: target sid={f['target_sid']} "
                f"is in a different document!"
            )

        if f["action"] == "move" and not f["target_wids"]:
            warnings.append(
                f"sid={sid} cid={cid}: move target has no matching wids"
            )

    return warnings


def process_language(lang: str, dry_run: bool) -> None:
    """Find and fix off-by-one concepts in one language database.

    Args:
        lang: Language code.
        dry_run: If True, report but don't modify.
    """
    db_path = BUILD_DIR / f"{lang}.db"
    if not db_path.exists():
        logger.warning("%s not found, skipping", lang)
        return

    conn = sqlite3.connect(str(db_path))
    findings = find_misplaced_concepts(conn)

    if not findings:
        logger.info("%s: no off-by-one errors found", lang)
        conn.close()
        return

    deletes = [f for f in findings if f["action"] == "delete"]
    moves = [f for f in findings if f["action"] == "move"]

    logger.info(
        "%s: %d off-by-one errors (%d duplicates to delete, %d to move)",
        lang, len(findings), len(deletes), len(moves),
    )

    for f in findings:
        action_str = "DELETE" if f["action"] == "delete" else f"MOVE→sid={f['target_sid']} wids={f['target_wids']}"
        logger.info(
            "  sid=%d cid=%d clemma=%s offset=%+d → %s",
            f["sid"], f["cid"], f["clemma"], f["offset"], action_str,
        )

    warnings = verify_fixes(conn, findings)
    if warnings:
        for w in warnings:
            logger.warning("  VERIFY: %s", w)
        if not dry_run:
            logger.error("  Aborting %s due to verification warnings", lang)
            conn.close()
            return

    if not dry_run:
        n_del, n_mov = apply_fixes(conn, findings, lang, dry_run=False)
        conn.commit()
        logger.info("%s: deleted %d, moved %d", lang, n_del, n_mov)
    else:
        logger.info(
            "%s: would delete %d, move %d", lang, len(deletes), len(moves),
        )

    conn.close()


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Fix off-by-one-sentence errors in concept-word links."
    )
    parser.add_argument("--fix", action="store_true", help="Apply changes")
    parser.add_argument("--dry-run", action="store_true", help="Report only")
    parser.add_argument(
        "--lang", nargs="+", default=ALL_LANGS,
        help=f"Languages to process (default: {' '.join(ALL_LANGS)})",
    )
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    for lang in args.lang:
        process_language(lang, dry_run=not args.fix)


if __name__ == "__main__":
    main()
