#!/usr/bin/env python3
"""Re-align cross-lingual concept links to post-merge corpus numbering.

Fixes https://github.com/bond-lab/NTUMC/issues/6: the clink rows that
import_links.py created reference concept ids from before the essay/kc
re-merge, the cmn spec/danc sid swap, and the jpn cid normalisation, so
thousands of endpoints are orphaned (and others silently point at the
wrong concept).

This script wipes the imported clink rows (all have usrname NULL — no
manual edits exist) and re-derives every link from the 2013 per-genre
sources directly against the *current* corpus databases:

  1. the old sentence is located in the live DB by exact text match
     (robust against every sid renumbering), falling back to the sid
     formula used at import time;
  2. the old concept is matched within that sentence by normalised
     clemma, disambiguated by tag and then by token position.

Usage:
    .venv/bin/python scripts/2026-07/realign_clinks.py --dry-run
    .venv/bin/python scripts/2026-07/realign_clinks.py --fix
"""

import argparse
import logging
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from import_links import SID_FORMULAS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# The 2013 source link tables carry no usrname column, so re-derived
# rows keep usrname NULL, exactly like the sources (annotator names on
# the live server postdate these files).  "realign-issue6" was the stamp
# an earlier run of this script used; it may still be wiped safely.
OLD_STAMP = "realign-issue6"
BUILD = Path(__file__).resolve().parents[2] / "build"
WORK = Path.home() / "work" / "ntu-mc"
SNAP = WORK / "2013-10-05"

# Same jobs as import_links.LINK_JOBS, but the concept databases come
# from the same 2013-10-05 snapshot as the link databases (the import
# paired them with older round0/round1 copies, whose corpus-wide cids
# do not cover all cids the link rows reference).  eng-dm keeps the
# round0 copy: the snapshot only has a renumbered variant.
LINK_JOBS = [
    ("eng-cmn essay", SNAP / "eng-cmn-essay-links.db",
     SNAP / "eng-essay.db", SNAP / "cmn-essay.db",
     "eng-essay", "cmn-essay",
     BUILD / "eng-cmn.db", BUILD / "eng.db", BUILD / "cmn.db"),
    ("eng-cmn dm", SNAP / "eng-cmn-dm-links.db",
     WORK / "round0" / "eng-dm.db", SNAP / "cmn-dm.db",
     "eng-dm", "cmn-dm",
     BUILD / "eng-cmn.db", BUILD / "eng.db", BUILD / "cmn.db"),
    ("eng-cmn story", SNAP / "eng-cmn-story-links.db",
     SNAP / "eng-story.db", SNAP / "cmn-story.db",
     "eng-story", "cmn-story",
     BUILD / "eng-cmn.db", BUILD / "eng.db", BUILD / "cmn.db"),
    ("eng-jpn essay", SNAP / "eng-jpn-essay-links.db",
     SNAP / "eng-essay.db", SNAP / "jpn-essay.db",
     "eng-essay", "jpn-essay",
     BUILD / "eng-jpn.db", BUILD / "eng.db", BUILD / "jpn.db"),
    ("eng-jpn dm", SNAP / "eng-jpn-dm-links.db",
     WORK / "round0" / "eng-dm.db", SNAP / "jpn-dm.db",
     "eng-dm", "jpn-dm",
     BUILD / "eng-jpn.db", BUILD / "eng.db", BUILD / "jpn.db"),
    ("eng-jpn story", SNAP / "eng-jpn-story-links.db",
     SNAP / "eng-story.db", SNAP / "jpn-story.db",
     "eng-story", "jpn-story",
     BUILD / "eng-jpn.db", BUILD / "eng.db", BUILD / "jpn.db"),
    ("eng-ind yoursing", SNAP / "eng-ind-yoursing-links.db",
     SNAP / "eng-yoursing.db", SNAP / "ind-yoursing.db",
     "eng-yoursing", "ind-yoursing",
     BUILD / "eng-ind.db", BUILD / "eng.db", BUILD / "ind.db"),
]


def norm_sent(text: object) -> str:
    """Normalise sentence text: collapse all whitespace."""
    return "".join(str(text if text is not None else "").split())


def norm(text: object) -> str:
    """Normalise a clemma for matching across renames.

    Old databases occasionally store numeric clemmas as integers.
    """
    return str(text if text is not None else "") \
        .replace("_", " ").strip().lower()


class OldCorpus:
    """Concept/sentence view of a 2013 per-genre database."""

    def __init__(self, db_path: Path, formula_key: str) -> None:
        """Load the old per-genre concept database.

        Args:
            db_path: Path to the old database (old schema: concept rows
                keyed (sid, wid, cid) with corpus-wide cid).
            formula_key: SID_FORMULAS key for the import-time renumbering.
        """
        self.formula = SID_FORMULAS[formula_key]
        conn = sqlite3.connect(str(db_path))
        self.sent: dict[int, str] = dict(
            conn.execute("SELECT sid, sent FROM sent"))
        self.word_rank: dict[int, dict[int, int]] = {}
        for sid, wid in conn.execute(
                "SELECT sid, wid FROM word ORDER BY sid, wid"):
            ranks = self.word_rank.setdefault(sid, {})
            ranks[wid] = len(ranks)
        # cid -> (sid, [wids], clemma, tag); MWE concepts repeat the cid
        self.concept: dict[int, tuple[int, list[int], str, str]] = {}
        for sid, wid, cid, clemma, tag in conn.execute(
                "SELECT sid, wid, cid, clemma, tag FROM concept"):
            if sid is None or cid is None:
                continue
            if cid in self.concept:
                self.concept[cid][1].append(wid)
            else:
                self.concept[cid] = (sid, [wid], clemma or "", tag or "")
        conn.close()


class LiveCorpus:
    """Lookup view of a current per-language corpus database."""

    def __init__(self, db_path: Path) -> None:
        """Index sentences, concepts and links of a live corpus DB."""
        conn = sqlite3.connect(str(db_path))
        self.sids_by_text: dict[str, list[int]] = defaultdict(list)
        self.sids_by_norm: dict[str, list[int]] = defaultdict(list)
        self.has_sid: set[int] = set()
        for sid, sent in conn.execute("SELECT sid, sent FROM sent"):
            self.has_sid.add(sid)
            if sent:
                self.sids_by_text[sent].append(sid)
                self.sids_by_norm[norm_sent(sent)].append(sid)
        # per sentence: concepts and their linked word ranks
        self.concepts: dict[int, list[tuple[int, str, str]]] = defaultdict(list)
        for sid, cid, clemma, tag in conn.execute(
                "SELECT sid, cid, clemma, tag FROM concept"):
            self.concepts[sid].append((cid, norm(clemma), tag or ""))
        self.word_rank: dict[int, dict[int, int]] = {}
        for sid, wid in conn.execute(
                "SELECT sid, wid FROM word ORDER BY sid, wid"):
            ranks = self.word_rank.setdefault(sid, {})
            ranks[wid] = len(ranks)
        self.cwl_ranks: dict[tuple[int, int], set[int]] = defaultdict(set)
        for sid, cid, wid in conn.execute("SELECT sid, cid, wid FROM cwl"):
            rank = self.word_rank.get(sid, {}).get(wid)
            if rank is not None:
                self.cwl_ranks[(sid, cid)].add(rank)
        conn.close()

    def sid_candidates(self, old_text: str | None,
                       formula_sid: int) -> list[int]:
        """Live sids that may correspond to an old sentence.

        Exact text matches first (robust against renumbering), then
        whitespace-normalised matches.  The import-time sid formula is
        only trusted when the live text at that sid actually matches —
        an unverified formula fallback pairs unrelated sentences in
        renumbered corpora (this caused the bogus eng-ind links).
        Boilerplate duplicates return several candidates — the caller
        disambiguates with slinks.
        """
        cands = list(self.sids_by_text.get(old_text or "", []))
        if not cands:
            cands = list(self.sids_by_norm.get(norm_sent(old_text), []))
        if formula_sid in cands:
            return [formula_sid]
        return cands

    def find_concept(self, sid: int, clemma: str, tag: str,
                     ranks: set[int]) -> tuple[int | None, str]:
        """Find the live cid for an old concept within a sentence.

        Args:
            sid: Live sentence id.
            clemma: Old concept clemma.
            tag: Old concept tag.
            ranks: Token positions (0-based ranks) of the old concept.

        Returns:
            (live_cid, reason) — cid is None when unresolved, and the
            reason names the failure class for reporting.
        """
        cands = [c for c in self.concepts.get(sid, ())
                 if c[1] == norm(clemma)]
        if len(cands) == 1:
            return cands[0][0], "clemma"
        if cands:
            tagged = [c for c in cands if c[2] == tag]
            if len(tagged) == 1:
                return tagged[0][0], "clemma+tag"
            pool = tagged or cands
            overlapping = [c for c in pool
                           if self.cwl_ranks.get((sid, c[0]), set()) & ranks]
            if len(overlapping) == 1:
                return overlapping[0][0], "clemma+position"
            return None, "ambiguous"
        # clemmas were renamed by later fixes (e.g. merge_ind): fall
        # back to token position, requiring a unique overlap
        overlapping = [c for c in self.concepts.get(sid, ())
                       if self.cwl_ranks.get((sid, c[0]), set()) & ranks]
        if len(overlapping) == 1:
            return overlapping[0][0], "position-only"
        by_tag = [c for c in overlapping if c[2] == tag]
        if len(by_tag) == 1:
            return by_tag[0][0], "position+tag"
        return None, "no-clemma-match"


def realign_job(name: str, link_db: Path, f_old_db: Path, t_old_db: Path,
                f_key: str, t_key: str, live_link_db: Path,
                f_live_db: Path, t_live_db: Path,
                live_cache: dict[Path, LiveCorpus],
                dry_run: bool) -> list[tuple]:
    """Resolve one old link database's clinks against the live corpora.

    Returns:
        Resolved rows (fsid, fcid, tsid, tcid, ltype, conf, comment).
    """
    for p in (link_db, f_old_db, t_old_db, live_link_db):
        if not p.exists():
            logger.warning("%s: missing %s, skipping", name, p)
            return []
    old_f = OldCorpus(f_old_db, f_key)
    old_t = OldCorpus(t_old_db, t_key)
    for live_path in (f_live_db, t_live_db):
        if live_path not in live_cache:
            live_cache[live_path] = LiveCorpus(live_path)
    live_f = live_cache[f_live_db]
    live_t = live_cache[t_live_db]

    conn = sqlite3.connect(str(link_db))
    old_clinks = conn.execute(
        "SELECT fcid, tcid, ltype, conf, comment FROM clink").fetchall()
    conn.close()

    live_conn = sqlite3.connect(str(live_link_db))
    live_slinks = {(r[0], r[1]) for r in live_conn.execute(
        "SELECT fsid, tsid FROM slink")}
    live_conn.close()

    def pick_pair(f_cands: list[int], t_cands: list[int]) -> tuple | None:
        """Choose the live sentence pair, preferring slink-linked pairs."""
        if len(f_cands) == 1 and len(t_cands) == 1:
            return f_cands[0], t_cands[0]
        on_slink = [(a, b) for a in f_cands for b in t_cands
                    if (a, b) in live_slinks]
        if len(on_slink) == 1:
            return on_slink[0]
        return None

    resolved: list[tuple] = []
    reasons: Counter = Counter()
    for fcid, tcid, ltype, conf, comment in old_clinks:
        f_meta = old_f.concept.get(fcid)
        t_meta = old_t.concept.get(tcid)
        if f_meta is None or t_meta is None:
            reasons["no-old-concept"] += 1
            continue
        f_cands = live_f.sid_candidates(old_f.sent.get(f_meta[0]),
                                        old_f.formula(f_meta[0]))
        t_cands = live_t.sid_candidates(old_t.sent.get(t_meta[0]),
                                        old_t.formula(t_meta[0]))
        if not f_cands or not t_cands:
            reasons["no-live-sentence"] += 1
            continue
        pair = pick_pair(f_cands, t_cands)
        if pair is None:
            reasons["sid-ambiguous"] += 1
            continue
        out = []
        for live_sid, meta, old, live in (
                (pair[0], f_meta, old_f, live_f),
                (pair[1], t_meta, old_t, live_t)):
            old_sid, wids, clemma, tag = meta
            ranks = {old.word_rank.get(old_sid, {}).get(w)
                     for w in wids} - {None}
            live_cid, how = live.find_concept(live_sid, clemma, tag, ranks)
            if live_cid is None:
                reasons[how] += 1
                break
            out.append((live_sid, live_cid))
        else:
            resolved.append((out[0][0], out[0][1], out[1][0], out[1][1],
                             ltype, conf, comment))
            reasons["resolved"] += 1
    logger.info("%s: %d/%d resolved  %s", name, len(resolved),
                len(old_clinks), dict(reasons))
    return resolved


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Re-align clinks to post-merge corpus numbering "
                    "(issue #6).")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true",
                       help="Resolve and report, change nothing")
    group.add_argument("--fix", action="store_true",
                       help="Rewrite the clink tables")
    args = parser.parse_args()

    live_cache: dict[Path, LiveCorpus] = {}
    per_target: dict[Path, list[tuple]] = defaultdict(list)
    for job in LINK_JOBS:
        (name, link_db, f_old, t_old, f_key, t_key,
         live_link, f_live, t_live) = job
        rows = realign_job(name, link_db, f_old, t_old, f_key, t_key,
                           live_link, f_live, t_live, live_cache,
                           args.dry_run)
        per_target[live_link].extend(rows)

    for live_link, rows in per_target.items():
        # dedupe on endpoints (ON CONFLICT IGNORE semantics of the source)
        unique = {}
        for r in rows:
            unique.setdefault((r[0], r[1], r[2], r[3]), r)
        conn = sqlite3.connect(str(live_link))
        n_manual = conn.execute(
            "SELECT COUNT(*) FROM clink WHERE usrname IS NOT NULL "
            "AND usrname != ?", (OLD_STAMP,)).fetchone()[0]
        if n_manual:
            logger.error("%s: %d clink rows carry a usrname — manual "
                         "edits present, refusing to wipe", live_link,
                         n_manual)
            conn.close()
            continue
        old_n = conn.execute("SELECT COUNT(*) FROM clink").fetchone()[0]
        logger.info("%s: %d clinks -> %d re-aligned%s", live_link, old_n,
                    len(unique), " (dry run)" if args.dry_run else "")
        if not args.dry_run:
            conn.execute("DELETE FROM clink")
            conn.executemany(
                "INSERT INTO clink (clid, fsid, fcid, tsid, tcid, ltype, "
                "conf, comment, usrname) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(i + 1, *r, None) for i, r in enumerate(unique.values())])
            conn.commit()
        conn.close()


if __name__ == "__main__":
    main()
