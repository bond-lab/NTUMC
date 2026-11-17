#!/usr/bin/env python3
"""Put back the senses a wordnet lacks that the corpus is tagged with.

    .venv/bin/python scripts/2026-11/restore_tagged_senses.py LANG BASE.xml CHANGES.jsonl \
        [--held HELD.tsv] [--apply]

Francis Bond's rule of 2026-11-17: nothing the corpus is tagged with is
taken out of a wordnet unless the corpus is fixed as well.  The sense
reviews and the releases' choice of sources took out senses that the
corpus uses, so they come back, each with a note that it is to be
checked: either the sense or the tag is wrong.

A sense comes back if the corpus database build/LANG.db has concepts
tagged with its synset and lemma, the wordnet database build/wn-ntumc.db
(frozen 2026-11-13) has it, and the wordnet (BASE.xml with the records
of CHANGES.jsonl) does not.  For each, records are added to
CHANGES.jsonl: ``add_synset`` if the wordnet has no such synset (with
its ILI, and no definition), ``add_sense``, and ``set_note`` with NOTE.
A sense whose records do not fit the wordnet (for instance a lemma with
two entries) is not added, and is listed in HELD.tsv.

Without --apply nothing is written.  Running it twice adds nothing more.
"""

import argparse
import csv
import logging
import sqlite3
from pathlib import Path

from ntumc.wordnet import changes, lmf
from ntumc.wordnet.changes import Change
from ntumc.wordnet.model import Entry, Lexicon, Synset

ROOT = Path(__file__).resolve().parent.parent.parent
ILI_MAP = ROOT / "build" / "ili-map-pwn30.tab"
WN_DB = ROOT / "build" / "wn-ntumc.db"
NOTE = "to check: taken out of the wordnet, but the NTU-MC is tagged with it"
SOURCE = "NTU-MC corpus: {n} concepts tagged with it; NTU-MC wordnet database, frozen 2026-11-13"
REASON = ("taken out of the wordnet, but the corpus is tagged with it; "
          "back until the sense and the tags are checked (Francis Bond, 2026-11-17)")
DATE = "2026-11-17"

log = logging.getLogger("restore")


def same(word: str, lang: str) -> str:
    """A word as it is compared: lower case; no spaces in Chinese and Japanese."""
    return ("" if lang in ("cmn", "jpn") else " ").join(word.replace("_", " ").lower().split())


def ilis() -> dict[str, str]:
    """The ILI of each Princeton WordNet 3.0 synset, by the corpus's synset id."""
    out = {}
    for line in ILI_MAP.read_text().splitlines():
        ili, offset = line.split()
        out[offset] = ili
        if offset.endswith("s"):  # the corpus has satellites as -a
            out[offset[:-1] + "a"] = ili
    return out


def tagged(lang: str) -> dict[tuple[str, str], int]:
    """How often the corpus uses each synset with each lemma, as (synset, lemma compared)."""
    con = sqlite3.connect(f"file:{ROOT / 'build' / f'{lang}.db'}?mode=ro", uri=True)
    uses: dict[tuple[str, str], int] = {}
    for tag, lemma, n in con.execute(
            "SELECT tag, clemma, COUNT(*) FROM concept "
            "WHERE tag GLOB '[0-9]*-[a-z]' AND clemma IS NOT NULL GROUP BY tag, clemma"):
        key = (tag, same(lemma, lang))
        uses[key] = uses.get(key, 0) + n
    con.close()
    return uses


def frozen(lang: str) -> dict[tuple[str, str], str]:
    """The lemma of each sense of the frozen wordnet database, by (synset, lemma compared)."""
    con = sqlite3.connect(f"file:{WN_DB}?mode=ro", uri=True)
    senses = {(synset, same(lemma, lang)): lemma for synset, lemma in con.execute(
        "SELECT s.synset, w.lemma FROM sense s JOIN word w ON w.wordid = s.wordid "
        "WHERE s.lang = ? ORDER BY s.confidence", (lang,))}
    con.close()
    return senses


def state(base: Path, records: list[Change]) -> tuple[str, set[str], set[tuple[str, str]]]:
    """The wordnet after its records: its id, its synsets and its senses."""
    items, conflicts = changes.apply(list(lmf.read(base)), records)
    if conflicts:
        raise ValueError(f"{len(conflicts)} conflicts before anything is added: {conflicts[0]}")
    lexicon = str(next(i for i in items if isinstance(i, Lexicon)).id)
    synsets = {str(i.id) for i in items if isinstance(i, Synset)}
    senses = {(str(s.synset), str(e.lemma)) for i in items if isinstance(i, Entry)
              for e in [i] for s in e.senses}
    return lexicon, synsets, senses


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("lang", help="the corpus's language, e.g. jpn")
    parser.add_argument("base", type=Path, help="the wordnet's base release (XML)")
    parser.add_argument("changes", type=Path, help="the wordnet's change log")
    parser.add_argument("--held", type=Path, help="where to list senses that do not fit")
    parser.add_argument("--apply", action="store_true", help="write the records")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    lang = args.lang
    records = list(changes.read(args.changes))
    lexicon, synsets, senses = state(args.base, records)
    have = {(synset.removeprefix(f"{lexicon}-"), same(lemma, lang)) for synset, lemma in senses}
    old, to_ili = frozen(lang), ilis()
    wanted = sorted((key, n) for key, n in tagged(lang).items() if key in old and key not in have)

    stem = args.changes.stem
    number = len(records)
    groups: list[tuple[tuple[str, str, int], list[Change]]] = []
    made: set[str] = set()
    for (tag, key), n in wanted:
        synset, lemma = f"{lexicon}-{tag}", old[(tag, key)]
        steps: list[dict[str, str]] = []
        if synset not in synsets and synset not in made:
            made.add(synset)
            steps.append({"action": "add_synset", "new": "", "ili": to_ili.get(tag, "")})
        steps.append({"action": "add_sense", "lemma": lemma})
        steps.append({"action": "set_note", "lemma": lemma, "new": NOTE})
        group = [Change(id=f"{stem}-{number + i}", lexicon=lexicon, synset=synset, pos=tag[-1],
                        user="fcbond", date=DATE, base=stem, source=SOURCE.format(n=n),
                        reason=REASON, **step) for i, step in enumerate(steps, 1)]
        number += len(group)
        groups.append(((tag, lemma, n), group))

    # a group that does not fit is held; its synset may be needed by a later one, so try again
    new = [c for _, group in groups for c in group]
    _, conflicts = changes.apply(list(lmf.read(args.base)), records + new)
    bad = {line.split(":")[0]: line for line in conflicts}
    kept, held = [], []
    for (tag, lemma, n), group in groups:
        problems = [bad[c.id] for c in group if c.id in bad]
        if problems:
            held.append((tag, lemma, n, problems[0].split(": ", 2)[-1]))
        else:
            kept += group
    for i, c in enumerate(kept, len(records) + 1):  # number again, with no gaps
        c.id = f"{stem}-{i}"
    _, conflicts = changes.apply(list(lmf.read(args.base)), records + kept)
    if conflicts:
        raise ValueError(f"{len(conflicts)} conflicts are left: {conflicts[0]}")

    senses_back = sum(c.action == "add_sense" for c in kept)
    log.info("%s: %d senses to put back (%d uses), %d new synsets; %d held",
             lexicon, senses_back, sum(n for (_, _, n), g in groups if g[0] in kept),
             sum(c.action == "add_synset" for c in kept), len(held))
    if args.held and held:
        with args.held.open("w", newline="", encoding="utf-8") as f:
            out = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, quotechar=None,
                             escapechar="\\")
            out.writerow(["synset", "lemma", "uses", "why_held"])
            out.writerows(held)
    if args.apply and kept:
        changes.write(args.changes, records + kept)
        log.info("Wrote %d records to %s", len(kept), args.changes)


if __name__ == "__main__":
    main()
