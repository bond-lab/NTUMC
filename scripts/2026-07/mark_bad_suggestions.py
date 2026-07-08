#!/usr/bin/env python3
"""Mark rejected comment suggestions in the corpus databases.

Appends a machine-readable rejection marker to the concept comment of
every suggestion judged BAD in a review pass:

    <original comment>; BAD[YYYY-MM-DD]: <reason>

The original suggestion text is preserved (it documents what was
proposed); the marker tells annotators the suggestion was reviewed and
rejected, and makes audit_comment_suggestions.py classify the row as
REJECTED so it is not re-reviewed.

Two verdict granularities are supported:
  * concept level (columns lang, sid, cid, verdict, reason) — e.g.
    docs/partly-verdicts.tsv;
  * type level (columns lang, clemma, op, synset, verdict, reason) —
    the wordnet-edit reviews; the marker is applied to every concept
    whose comment carries that suggestion (via comment-suggestions.tsv).

Usage:
    .venv/bin/python scripts/2026-07/mark_bad_suggestions.py \
        docs/partly-verdicts.tsv --dry-run
    .venv/bin/python scripts/2026-07/mark_bad_suggestions.py \
        docs/partly-verdicts.tsv --fix
"""

import argparse
import csv
import datetime
import logging
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
SUGGESTIONS = ROOT / "docs" / "comment-suggestions.tsv"


def concepts_for_type(lang: str, clemma: str,
                      suggestion: str) -> list[tuple[int, int]]:
    """All (sid, cid) whose comment carries this suggestion type."""
    hits = []
    with open(SUGGESTIONS, encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            if (r["lang"] == lang
                    and (r["clemma"] or "").strip() == clemma
                    and r["suggestion"] == suggestion):
                hits.append((int(r["sid"]), int(r["cid"])))
    return hits


def load_bad(verdict_file: Path) -> dict[str, list[tuple[int, int, str]]]:
    """Collect BAD rows as {lang: [(sid, cid, reason)]}."""
    per_lang: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    with open(verdict_file, encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        cols = set(reader.fieldnames or ())
        concept_level = {"sid", "cid"} <= cols
        if not concept_level and not {"clemma", "synset"} <= cols:
            raise SystemExit(f"unrecognised verdict columns: {cols}")
        for r in reader:
            if r["verdict"] != "BAD":
                continue
            reason = (r.get("reason") or "").strip()
            if concept_level:
                per_lang[r["lang"]].append(
                    (int(r["sid"]), int(r["cid"]), reason))
            else:
                sugg = (r.get("op") or "=") + r["synset"]
                for sid, cid in concepts_for_type(
                        r["lang"], (r["clemma"] or "").strip(), sugg):
                    per_lang[r["lang"]].append((sid, cid, reason))
    return per_lang


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Append BAD[date] markers to rejected suggestions.")
    parser.add_argument("verdicts", type=Path, help="Verdict TSV")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--fix", action="store_true")
    args = parser.parse_args()

    stamp = datetime.date.today().isoformat()
    per_lang = load_bad(args.verdicts)
    counts: Counter = Counter()
    for lang, rows in sorted(per_lang.items()):
        conn = sqlite3.connect(str(BUILD / f"{lang}.db"))
        for sid, cid, reason in sorted(set(rows)):
            cur = conn.execute(
                "SELECT comment FROM concept WHERE sid = ? AND cid = ?",
                (sid, cid)).fetchone()
            if cur is None:
                logger.warning("%s %d/%d: concept gone, skipped",
                               lang, sid, cid)
                counts["skipped"] += 1
                continue
            comment = cur[0] or ""
            if "BAD[" in comment:
                counts["already"] += 1
                continue
            marker = f"; BAD[{stamp}]: {reason}" if reason \
                else f"; BAD[{stamp}]"
            if args.dry_run:
                logger.info("would mark %s %d/%d: ...%r", lang, sid, cid,
                            (comment[-40:] + marker))
            else:
                conn.execute(
                    "UPDATE concept SET comment = ? "
                    "WHERE sid = ? AND cid = ?",
                    (comment + marker, sid, cid))
            counts[lang] += 1
        if args.fix:
            conn.commit()
        conn.close()

    verb = "would mark" if args.dry_run else "marked"
    logger.info("%s %s; already marked: %d, skipped: %d", verb,
                {k: v for k, v in counts.items()
                 if k not in ("already", "skipped")},
                counts["already"], counts["skipped"])


if __name__ == "__main__":
    main()
