#!/usr/bin/env python3
"""Retag concepts whose comment suggestions were verified as correct.

Applies the PARTLY class from the comment-suggestion triage
(audit_comment_suggestions.py): concepts still carrying a placeholder
tag whose suggested synset already exists in the wordnet with the
lemma present.  Only rows judged GOOD in the LLM verification pass
(docs/partly-verdicts.tsv) are applied — a review showed ~21% of
mechanically-valid suggestions are semantically wrong, so the verdict
file is a required input, not an optional one.

Safety at apply time, per concept:
  * the current tag must still be a placeholder (x/w/e/...);
  * the suggested synset must still exist in wn-ntumc.db.
Anything that fails is skipped and logged.  Comments are left
untouched; the next triage run classifies retagged rows as DONE.

Usage:
    .venv/bin/python scripts/2026-07/retag_partly.py --dry-run
    .venv/bin/python scripts/2026-07/retag_partly.py --fix
"""

import argparse
import csv
import logging
import sqlite3
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build"
SUGGESTIONS = ROOT / "docs" / "comment-suggestions.tsv"
VERDICTS = ROOT / "docs" / "partly-verdicts.tsv"
PLACEHOLDER_TAGS = {"", "x", "w", "e", "u", "m", "s", "p",
                    "nam", "per", "org", "dat", "num", "oth"}


def load_targets() -> dict[tuple[str, int, int], str]:
    """Map GOOD-verdict concepts to their suggested synset.

    Returns:
        {(lang, sid, cid): synset} for every PARTLY suggestion whose
        verdict is GOOD.
    """
    good: set[tuple[str, str, str]] = set()
    with open(VERDICTS, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["verdict"] == "GOOD":
                good.add((row["lang"], row["sid"], row["cid"]))
    targets: dict[tuple[str, int, int], str] = {}
    with open(SUGGESTIONS, encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row["class"] != "PARTLY":
                continue
            if (row["lang"], row["sid"], row["cid"]) not in good:
                continue
            key = (row["lang"], int(row["sid"]), int(row["cid"]))
            targets.setdefault(key, row["suggestion"].lstrip("=<~"))
    return targets


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Retag verified-GOOD PARTLY suggestions.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Report what would change, change nothing")
    group.add_argument("--fix", action="store_true",
                       help="Apply the retagging")
    args = parser.parse_args()

    targets = load_targets()
    logger.info("verified GOOD suggestions to apply: %d", len(targets))

    wn = sqlite3.connect(str(BUILD / "wn-ntumc.db"))
    synsets = {r[0] for r in wn.execute("SELECT DISTINCT synset FROM synset")}
    wn.close()

    by_lang: dict[str, list[tuple[int, int, str]]] = {}
    for (lang, sid, cid), synset in sorted(targets.items()):
        by_lang.setdefault(lang, []).append((sid, cid, synset))

    counts: Counter = Counter()
    for lang, rows in by_lang.items():
        conn = sqlite3.connect(str(BUILD / f"{lang}.db"))
        for sid, cid, synset in rows:
            cur = conn.execute(
                "SELECT tag, clemma FROM concept WHERE sid = ? AND cid = ?",
                (sid, cid)).fetchone()
            if cur is None:
                logger.warning("%s %d/%d: concept gone, skipped",
                               lang, sid, cid)
                counts["skipped"] += 1
                continue
            tag, clemma = cur
            if tag == synset:
                counts["already"] += 1
                continue
            if (tag or "") not in PLACEHOLDER_TAGS:
                logger.warning("%s %d/%d (%s): tag changed to %r since "
                               "triage, skipped", lang, sid, cid, clemma, tag)
                counts["skipped"] += 1
                continue
            if synset not in synsets:
                logger.warning("%s %d/%d: synset %s no longer in wordnet, "
                               "skipped", lang, sid, cid, synset)
                counts["skipped"] += 1
                continue
            if args.dry_run:
                logger.info("would retag %s %d/%d %r: %r -> %s",
                            lang, sid, cid, clemma, tag, synset)
            else:
                conn.execute(
                    "UPDATE concept SET tag = ? WHERE sid = ? AND cid = ?",
                    (synset, sid, cid))
            counts[lang] += 1
        if not args.dry_run:
            conn.commit()
        conn.close()

    verb = "would retag" if args.dry_run else "retagged"
    logger.info("%s %s; already done: %d, skipped: %d", verb,
                {k: v for k, v in counts.items()
                 if k not in ("already", "skipped")},
                counts["already"], counts["skipped"])


if __name__ == "__main__":
    main()
