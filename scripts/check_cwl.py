#!/usr/bin/env python3
"""Check for suspect concept–word links (cwl) in corpus databases.

Flags two kinds of problems:

1. **Non-contiguous spans**: a concept is linked to multiple words whose
   wids have gaps (e.g. wids 13, 15, 22).  Legitimate MWEs have contiguous
   wids; gaps usually mean unrelated words were accidentally tagged with
   the same concept.  Use --min-gap to control sensitivity:
     - gap=1 catches everything (phrasal verbs like "throw X away")
     - gap>=n_words (the default) catches the clearly wrong ones

2. **Clemma mismatch**: the concept's clemma (with underscores/spaces
   removed) doesn't match the concatenation of the linked words' lemmas.
   Filters out known-OK patterns (named entities, metalinguistic tags).

Usage:
    .venv/bin/python scripts/check_cwl.py                  # default: gap >= n_words
    .venv/bin/python scripts/check_cwl.py --min-gap 1      # all non-contiguous
    .venv/bin/python scripts/check_cwl.py --min-gap 3      # gaps of 3+
    .venv/bin/python scripts/check_cwl.py --lang jpn eng
    .venv/bin/python scripts/check_cwl.py --contiguous-only # skip clemma check
"""

import argparse
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
ALL_LANGS = ["eng", "cmn", "jpn", "ind", "ita", "ces"]


def check_noncontiguous(
    conn: sqlite3.Connection,
    min_gap: int = 0,
) -> list[dict]:
    """Find concepts linked to non-contiguous word spans.

    Args:
        conn: Database connection.
        min_gap: Minimum gap size (span - n_words) to report.
            0 means "gap >= n_words" (the default heuristic).

    Returns:
        List of finding dicts.
    """
    if min_gap > 0:
        having = f"n_words > 1 AND (span - n_words) >= {min_gap}"
    else:
        having = "n_words > 1 AND (span - n_words) >= n_words"

    rows = conn.execute(f"""
        SELECT c.sid, c.cid, c.clemma, c.tag,
               GROUP_CONCAT(cwl.wid) AS wids,
               GROUP_CONCAT(w.word, '·') AS words,
               GROUP_CONCAT(w.lemma, '·') AS lemmas,
               COUNT(cwl.wid) AS n_words,
               MAX(cwl.wid) - MIN(cwl.wid) + 1 AS span
        FROM concept c
        JOIN cwl ON cwl.sid = c.sid AND cwl.cid = c.cid
        JOIN word w ON w.sid = cwl.sid AND w.wid = cwl.wid
        GROUP BY c.sid, c.cid
        HAVING {having}
        ORDER BY (MAX(cwl.wid) - MIN(cwl.wid) + 1 - COUNT(cwl.wid)) DESC,
                 c.sid, c.cid
    """).fetchall()

    findings = []
    for sid, cid, clemma, tag, wids, words, lemmas, n, span in rows:
        findings.append({
            "type": "NON_CONTIGUOUS",
            "sid": sid,
            "cid": cid,
            "clemma": clemma,
            "tag": tag,
            "wids": wids,
            "words": words,
            "lemmas": lemmas,
            "n_words": n,
            "gap": span - n,
        })

    return findings


def check_clemma_mismatch(conn: sqlite3.Connection) -> list[dict]:
    """Find multi-word concepts where clemma doesn't match word lemmas.

    Checks both contiguous and non-contiguous spans.  A concept is
    flagged when the clemma (underscores removed) neither equals nor
    is a reasonable substring match for the concatenated word lemmas.

    For non-contiguous spans, substring matching is tightened: the
    number of clemma parts must be close to the number of linked words,
    otherwise a short clemma trivially matches inside a long unrelated
    concatenation (e.g. clemma "続々" inside "続々生み出せるずばり").

    Args:
        conn: Database connection.

    Returns:
        List of finding dicts.
    """
    rows = conn.execute("""
        SELECT c.sid, c.cid, c.clemma, c.tag,
               GROUP_CONCAT(cwl.wid) AS wids,
               GROUP_CONCAT(w.word, '·') AS words,
               GROUP_CONCAT(w.lemma, '') AS lemma_concat,
               COUNT(cwl.wid) AS n_words,
               MAX(cwl.wid) - MIN(cwl.wid) + 1 AS span
        FROM concept c
        JOIN cwl ON cwl.sid = c.sid AND cwl.cid = c.cid
        JOIN word w ON w.sid = cwl.sid AND w.wid = cwl.wid
        GROUP BY c.sid, c.cid
        HAVING n_words > 1
        ORDER BY c.sid, c.cid
    """).fetchall()

    skip_tags = {"e", "u", "m", "h", "s", "x", "w", "org", "per", "dat", "oth", "num"}

    findings = []
    for sid, cid, clemma, tag, wids, words, lemma_concat, n, span in rows:
        if tag in skip_tags:
            continue

        norm_clemma = clemma.replace("_", "").replace(" ", "").lower()
        norm_lemmas = lemma_concat.lower()
        norm_words = words.replace("·", "").lower()
        is_contiguous = (span == n)

        if norm_clemma == norm_lemmas or norm_clemma == norm_words:
            continue

        clemma_parts = max(1, len(clemma.split("_")))

        if is_contiguous:
            if (norm_clemma in norm_lemmas or norm_lemmas in norm_clemma
                    or norm_clemma in norm_words or norm_words in norm_clemma):
                continue
        else:
            if n <= clemma_parts + 1:
                if (norm_clemma in norm_lemmas or norm_lemmas in norm_clemma
                        or norm_clemma in norm_words or norm_words in norm_clemma):
                    continue

        findings.append({
            "type": "CLEMMA_MISMATCH",
            "sid": sid,
            "cid": cid,
            "clemma": clemma,
            "tag": tag,
            "wids": wids,
            "words": words,
            "lemmas": lemma_concat,
            "n_words": n,
            "gap": span - n,
        })

    return findings


def check_database(
    db_path: Path,
    contiguous_only: bool = False,
    min_gap: int = 0,
) -> list[dict]:
    """Run all checks on one database.

    Args:
        db_path: Path to the corpus database.
        contiguous_only: If True, only check for non-contiguous spans.
        min_gap: Passed to check_noncontiguous.

    Returns:
        List of finding dicts.
    """
    if not db_path.exists():
        logger.warning("%s not found, skipping", db_path)
        return []

    conn = sqlite3.connect(str(db_path))
    findings = check_noncontiguous(conn, min_gap=min_gap)
    if not contiguous_only:
        findings.extend(check_clemma_mismatch(conn))
    conn.close()
    return findings


def print_findings(lang: str, findings: list[dict], verbose: bool = False) -> None:
    """Print findings for one language.

    Args:
        lang: Language code.
        findings: List of finding dicts.
        verbose: If True, print every finding; otherwise just the summary.
    """
    if not findings:
        print(f"\n  {lang}: no issues found")
        return

    noncontig = [f for f in findings if f["type"] == "NON_CONTIGUOUS"]
    mismatch = [f for f in findings if f["type"] == "CLEMMA_MISMATCH"]

    print(f"\n  {lang}: {len(findings)} issues "
          f"({len(noncontig)} non-contiguous, {len(mismatch)} clemma mismatch)")

    if not verbose:
        return

    if noncontig:
        print(f"\n  Non-contiguous spans ({len(noncontig)}):")
        for f in noncontig:
            print(f"    sid={f['sid']:>6d} cid={f['cid']:>5d} "
                  f"gap={f['gap']:>2d}  "
                  f"clemma={f['clemma']:<20s} "
                  f"wids=[{f['wids']}] "
                  f"words=[{f['words']}] "
                  f"tag={f['tag']}")

    if mismatch:
        print(f"\n  Clemma mismatches ({len(mismatch)}):")
        for f in mismatch:
            print(f"    sid={f['sid']:>6d} cid={f['cid']:>5d} "
                  f"clemma={f['clemma']:<20s} "
                  f"lemmas={f['lemmas']:<20s} "
                  f"words=[{f['words']}] "
                  f"tag={f['tag']}")


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Check for suspect concept-word links in corpus databases."
    )
    parser.add_argument(
        "--lang", nargs="+", default=ALL_LANGS,
        help=f"Languages to check (default: {' '.join(ALL_LANGS)})",
    )
    parser.add_argument(
        "--min-gap", type=int, default=0,
        help="Minimum gap to report (default: gap >= n_words heuristic; "
             "use 1 for all non-contiguous)",
    )
    parser.add_argument(
        "--contiguous-only", action="store_true",
        help="Only check for non-contiguous word spans (skip clemma check)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print each finding (default: summary counts only)",
    )
    args = parser.parse_args()

    gap_desc = (f"gap >= n_words" if args.min_gap == 0
                else f"gap >= {args.min_gap}")
    print("=" * 70)
    print(f"  CWL (concept-word link) audit  [{gap_desc}]")
    print("=" * 70)

    total = 0
    for lang in args.lang:
        db_path = BUILD_DIR / f"{lang}.db"
        findings = check_database(
            db_path, args.contiguous_only, min_gap=args.min_gap,
        )
        print_findings(lang, findings, verbose=args.verbose)
        total += len(findings)

    print(f"\n  Total: {total} issues across {len(args.lang)} language(s)")
    print()


if __name__ == "__main__":
    main()
