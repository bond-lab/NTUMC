#!/usr/bin/env python3
"""Add to a wordnet's change records the merges the Open English Wordnet made.

    .venv/bin/python scripts/2026-11/oewn_merge_records.py RELEASE.xml CHANGES.jsonl

RELEASE.xml is the wordnet as its change records build it now.  For each
pair of oewn-merges.tsv (beside this script) whose old synset the
wordnet has, a ``merge_synset`` record is appended to CHANGES.jsonl,
after an ``add_synset`` for the synset that took its place if the
wordnet does not have that yet.  The corpus tags were moved the same way
(retag_oewn_merges.py), so the words must follow.

Francis Bond asked for this on 2026-11-16.
"""

import argparse
import csv
import logging
import re
from pathlib import Path

from ntumc.wordnet import changes, lmf
from ntumc.wordnet.changes import Change
from ntumc.wordnet.model import Lexicon, Synset

MERGES = Path(__file__).with_name("oewn-merges.tsv")
SOURCE = "Open English Wordnet 2025+, src/deprecations.csv"

log = logging.getLogger("merges")


def records(xml: Path, log_path: Path) -> list[Change]:
    """The change records that merge the synsets OEWN merged.

    Args:
        xml: the wordnet built from its change records
        log_path: its change records, for the ids, base and lexicon to use

    Returns:
        The new records, numbered on from the last one of the log
    """
    items = list(lmf.read(xml))
    lexicon = str(next(i for i in items if isinstance(i, Lexicon)).id).removesuffix("-min")
    by_ili = {s.ili: s for s in items if isinstance(s, Synset) and s.ili}
    old = list(changes.read(log_path))
    stem, number = re.fullmatch(r"(.*-)(\d+)", str(old[-1].id)).groups()
    out: list[Change] = []

    def add(**fields: str | None) -> None:
        out.append(Change(id=f"{stem}{int(number) + len(out) + 1}", lexicon=lexicon,
                          user="fcbond", date="2026-11-16", base=old[-1].base, **fields))

    with MERGES.open(newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            synset = by_ili.get(row["old_ili"])
            if synset is None:
                continue
            target = by_ili.get(row["new_ili"])
            name = str(target.id) if target is not None else re.sub(
                r"\d{8}", row["new_tag"][:8], str(synset.id))
            if target is None:
                add(action="add_synset", synset=name, pos=str(synset.pos), new="",
                    ili=row["new_ili"], source=SOURCE,
                    reason=f"to take the words of {row['old_ili']}, which OEWN merged into it")
            add(action="merge_synset", synset=str(synset.id), target=name,
                source=f"{SOURCE}: {row['oewn_reason']}",
                reason=f"OEWN merged {row['old_ili']} into {row['new_ili']}; "
                       "the corpus tags were moved the same way")
    return out


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("xml", type=Path, help="the wordnet as built now")
    parser.add_argument("changes", type=Path, help="its change records, to append to")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    new = records(args.xml, args.changes)
    with args.changes.open("a", encoding="utf-8") as f:
        f.writelines(changes.dumps(c) + "\n" for c in new)
    log.info("%d records added to %s", len(new), args.changes)


if __name__ == "__main__":
    main()
