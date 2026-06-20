#!/usr/bin/env python3
"""Import cross-lingual concept and word links from old per-genre databases.

The 2015 merge into per-language databases preserved sentence links (slinks)
but dropped all concept links (clinks) and word links (wlinks).  This script
recovers them from the 2013 per-genre link databases by mapping old
corpus-wide cids/wids to (sid, cid)/(sid, wid) pairs in the live databases.

Usage:
    .venv/bin/python scripts/import_links.py --dry-run
    .venv/bin/python scripts/import_links.py --fix
"""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
WORK_DIR = Path.home() / "work" / "ntu-mc"

# ---------------------------------------------------------------------------
# Sid renumbering formulas for each old per-genre corpus
# ---------------------------------------------------------------------------

SID_FORMULAS: dict[str, callable] = {
    "eng-essay": lambda sid: sid - 100,        # 101-869 → 1-769
    "eng-story": lambda sid: sid,              # 10000-11607 → same
    "eng-dm": lambda sid: sid // 10 + 10899,   # 1010-7080 → 11000-11607
    "eng-yoursing": lambda sid: sid,           # 100000+ → same
    "cmn-essay": lambda sid: sid + 1,          # 0-815 → 1-816
    "cmn-story": lambda sid: sid,              # 10000-11619 → same
    "cmn-dm": lambda sid: sid + 8000,          # 2000-2605 → 10000-10605
    "jpn-essay": lambda sid: sid,              # 1-773 → same
    "jpn-story": lambda sid: sid,              # 10000-10701 → same
    "jpn-dm": lambda sid: sid + 10000,         # 1000-1697 → 11000-11697
    "ind-yoursing": lambda sid: sid,           # 100000+ → same
}

# ---------------------------------------------------------------------------
# Link DB definitions
# ---------------------------------------------------------------------------

# (name, link_db_path, source_concept_db, target_concept_db,
#  source_key, target_key, live_link_db)
LINK_JOBS = [
    (
        "eng-cmn essay",
        WORK_DIR / "2013-10-05" / "eng-cmn-essay-links.db",
        WORK_DIR / "round1" / "eng-essay.db",
        WORK_DIR / "round0" / "cmn-catb.db",
        "eng-essay", "cmn-essay",
        BUILD_DIR / "eng-cmn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "cmn.db",
    ),
    (
        "eng-cmn dm",
        WORK_DIR / "2013-10-05" / "eng-cmn-dm-links.db",
        WORK_DIR / "round0" / "eng-dm.db",
        WORK_DIR / "round0" / "cmn-dm.db",
        "eng-dm", "cmn-dm",
        BUILD_DIR / "eng-cmn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "cmn.db",
    ),
    (
        "eng-cmn story",
        WORK_DIR / "2013-10-05" / "eng-cmn-story-links.db",
        WORK_DIR / "round1" / "eng-story.db",
        WORK_DIR / "round1" / "cmn-story.db",
        "eng-story", "cmn-story",
        BUILD_DIR / "eng-cmn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "cmn.db",
    ),
    (
        "eng-jpn essay",
        WORK_DIR / "2013-10-05" / "eng-jpn-essay-links.db",
        WORK_DIR / "round1" / "eng-essay.db",
        WORK_DIR / "round0" / "jpn-catb.db",
        "eng-essay", "jpn-essay",
        BUILD_DIR / "eng-jpn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "jpn.db",
    ),
    (
        "eng-jpn dm",
        WORK_DIR / "2013-10-05" / "eng-jpn-dm-links.db",
        WORK_DIR / "round0" / "eng-dm.db",
        WORK_DIR / "round0" / "jpn-dm.db",
        "eng-dm", "jpn-dm",
        BUILD_DIR / "eng-jpn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "jpn.db",
    ),
    (
        "eng-jpn story",
        WORK_DIR / "2013-10-05" / "eng-jpn-story-links.db",
        WORK_DIR / "round1" / "eng-story.db",
        WORK_DIR / "round0" / "jpn-story.db",
        "eng-story", "jpn-story",
        BUILD_DIR / "eng-jpn.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "jpn.db",
    ),
    (
        "eng-ind yoursing",
        WORK_DIR / "2013-10-05" / "eng-ind-yoursing-links.db",
        WORK_DIR / "round0" / "eng-yoursing.db",
        WORK_DIR / "round0" / "ind-yoursing.db",
        "eng-yoursing", "ind-yoursing",
        BUILD_DIR / "eng-ind.db",
        BUILD_DIR / "eng.db", BUILD_DIR / "ind.db",
    ),
]


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------


def build_cid_map(concept_db: Path, key: str) -> dict[int, tuple[int, str]]:
    """Build old corpus-wide cid → (new_sid, clemma) mapping.

    Args:
        concept_db: Path to old per-genre concept database.
        key: Key into SID_FORMULAS for sid renumbering.

    Returns:
        {old_cid: (new_sid, clemma)}
    """
    formula = SID_FORMULAS[key]
    conn = sqlite3.connect(str(concept_db))
    result: dict[int, tuple[int, str]] = {}
    for sid, cid, clemma in conn.execute(
        "SELECT DISTINCT sid, cid, clemma FROM concept"
    ).fetchall():
        if sid is not None:
            result[cid] = (formula(sid), clemma or "")
    conn.close()
    return result


def build_wid_to_sid(concept_db: Path, key: str) -> dict[int, int]:
    """Build old corpus-wide wid → new sid mapping.

    Args:
        concept_db: Path to old per-genre concept database.
        key: Key into SID_FORMULAS for sid renumbering.

    Returns:
        {old_wid: new_sid}
    """
    formula = SID_FORMULAS[key]
    conn = sqlite3.connect(str(concept_db))
    result = {}
    for sid, wid in conn.execute("SELECT DISTINCT sid, wid FROM concept").fetchall():
        if sid is not None:
            result[wid] = formula(sid)
    conn.close()
    return result


class LiveDBCache:
    """Cache of concept and word lookups for live databases."""

    def __init__(self):
        self._concepts: dict[str, set[tuple[int, int]]] = {}
        self._concept_by_clemma: dict[str, dict[tuple[int, str], int]] = {}
        self._words: dict[str, set[tuple[int, int]]] = {}

    def _load_concepts(self, live_db: Path) -> None:
        key = str(live_db)
        if key in self._concepts:
            return
        conn = sqlite3.connect(str(live_db))
        self._concepts[key] = {
            (r[0], r[1])
            for r in conn.execute("SELECT sid, cid FROM concept").fetchall()
        }
        self._concept_by_clemma[key] = {}
        for sid, cid, clemma in conn.execute(
            "SELECT sid, cid, clemma FROM concept"
        ).fetchall():
            self._concept_by_clemma[key][(sid, clemma)] = cid
        conn.close()

    def _load_words(self, live_db: Path) -> None:
        key = str(live_db)
        if key in self._words:
            return
        conn = sqlite3.connect(str(live_db))
        self._words[key] = {
            (r[0], r[1])
            for r in conn.execute("SELECT sid, wid FROM word").fetchall()
        }
        conn.close()

    def has_concept(self, live_db: Path, sid: int, cid: int) -> bool:
        """Check if (sid, cid) exists in the live concept table."""
        self._load_concepts(live_db)
        return (sid, cid) in self._concepts[str(live_db)]

    def resolve_concept(
        self, live_db: Path, sid: int, old_cid: int, clemma: str
    ) -> int | None:
        """Resolve an old corpus-wide cid to the live per-sentence cid.

        Tries direct match first, then falls back to clemma matching.

        Returns:
            The live cid, or None if unresolvable.
        """
        self._load_concepts(live_db)
        key = str(live_db)
        if (sid, old_cid) in self._concepts[key]:
            return old_cid
        live_cid = self._concept_by_clemma[key].get((sid, clemma))
        return live_cid

    def has_word(self, live_db: Path, sid: int, wid: int) -> bool:
        """Check if (sid, wid) exists in the live word table."""
        self._load_words(live_db)
        return (sid, wid) in self._words[str(live_db)]


_cache = LiveDBCache()


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------


def import_links_for_job(
    name: str,
    link_db: Path,
    f_concept_db: Path, t_concept_db: Path,
    f_key: str, t_key: str,
    live_link_db: Path,
    f_live_db: Path, t_live_db: Path,
    dry_run: bool = False,
) -> int:
    """Import clinks and wlinks from one old per-genre link database.

    Args:
        name: Human-readable job name.
        link_db: Path to old per-genre link database.
        f_concept_db: Old source-language concept database.
        t_concept_db: Old target-language concept database.
        f_key: SID_FORMULAS key for source language.
        t_key: SID_FORMULAS key for target language.
        live_link_db: Path to live link database to write into.
        f_live_db: Live source-language corpus database (for validation).
        t_live_db: Live target-language corpus database (for validation).
        dry_run: If True, count but don't insert.

    Returns:
        Number of rows inserted.
    """
    for p in (link_db, f_concept_db, t_concept_db, live_link_db):
        if not p.exists():
            logger.warning("%s: missing %s, skipping", name, p)
            return 0

    old_conn = sqlite3.connect(str(link_db))
    old_tables = {
        r[0] for r in old_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    changes = 0

    # --- clinks ---
    if "clink" in old_tables:
        old_clinks = old_conn.execute(
            "SELECT fcid, tcid, ltype, conf, comment FROM clink"
        ).fetchall()

        if old_clinks:
            f_map = build_cid_map(f_concept_db, f_key)
            t_map = build_cid_map(t_concept_db, t_key)

            live_conn = sqlite3.connect(str(live_link_db))
            existing_clinks = set()
            try:
                existing_clinks = {
                    (r[0], r[1], r[2], r[3])
                    for r in live_conn.execute(
                        "SELECT fsid, fcid, tsid, tcid FROM clink"
                    ).fetchall()
                }
            except sqlite3.OperationalError:
                pass

            max_clid = 0
            try:
                r = live_conn.execute("SELECT COALESCE(MAX(clid), 0) FROM clink").fetchone()
                max_clid = r[0]
            except sqlite3.OperationalError:
                pass

            new_clinks = []
            skipped = 0
            for fcid, tcid, ltype, conf, comment in old_clinks:
                f_info = f_map.get(fcid)
                t_info = t_map.get(tcid)
                if f_info is None or t_info is None:
                    skipped += 1
                    continue
                fsid, f_clemma = f_info
                tsid, t_clemma = t_info
                live_fcid = _cache.resolve_concept(f_live_db, fsid, fcid, f_clemma)
                live_tcid = _cache.resolve_concept(t_live_db, tsid, tcid, t_clemma)
                if live_fcid is None or live_tcid is None:
                    skipped += 1
                    continue
                if (fsid, live_fcid, tsid, live_tcid) in existing_clinks:
                    continue
                max_clid += 1
                new_clinks.append(
                    (max_clid, fsid, live_fcid, tsid, live_tcid,
                     ltype, conf, comment, None)
                )

            if new_clinks:
                logger.info(
                    "%s: %s %d clinks (%d skipped, %d already present)",
                    name, "would import" if dry_run else "importing",
                    len(new_clinks), skipped,
                    len(old_clinks) - len(new_clinks) - skipped,
                )
                if not dry_run:
                    live_conn.executemany(
                        "INSERT INTO clink (clid, fsid, fcid, tsid, tcid, "
                        "ltype, conf, comment, usrname) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        new_clinks,
                    )
                changes += len(new_clinks)
            elif skipped:
                logger.info(
                    "%s: %d clinks all unresolvable (%d skipped)",
                    name, len(old_clinks), skipped,
                )

            if not dry_run and new_clinks:
                live_conn.commit()
            live_conn.close()

    # --- wlinks ---
    if "wlink" in old_tables:
        old_wlinks = old_conn.execute(
            "SELECT fwid, twid, ltype, conf, comment FROM wlink"
        ).fetchall()

        if old_wlinks:
            f_wmap = build_wid_to_sid(f_concept_db, f_key)
            t_wmap = build_wid_to_sid(t_concept_db, t_key)

            live_conn = sqlite3.connect(str(live_link_db))
            existing_wlinks = set()
            try:
                existing_wlinks = {
                    (r[0], r[1], r[2], r[3])
                    for r in live_conn.execute(
                        "SELECT fsid, fwid, tsid, twid FROM wlink"
                    ).fetchall()
                }
            except sqlite3.OperationalError:
                pass

            max_wlid = 0
            try:
                r = live_conn.execute("SELECT COALESCE(MAX(wlid), 0) FROM wlink").fetchone()
                max_wlid = r[0]
            except sqlite3.OperationalError:
                pass

            new_wlinks = []
            skipped = 0
            for fwid, twid, ltype, conf, comment in old_wlinks:
                fsid = f_wmap.get(fwid)
                tsid = t_wmap.get(twid)
                if fsid is None or tsid is None:
                    skipped += 1
                    continue
                if not _cache.has_word(f_live_db, fsid, fwid):
                    skipped += 1
                    continue
                if not _cache.has_word(t_live_db, tsid, twid):
                    skipped += 1
                    continue
                if (fsid, fwid, tsid, twid) in existing_wlinks:
                    continue
                max_wlid += 1
                new_wlinks.append(
                    (max_wlid, fsid, fwid, tsid, twid, ltype, conf, comment, None)
                )

            if new_wlinks:
                logger.info(
                    "%s: %s %d wlinks (%d skipped)",
                    name, "would import" if dry_run else "importing",
                    len(new_wlinks), skipped,
                )
                if not dry_run:
                    live_conn.executemany(
                        "INSERT INTO wlink (wlid, fsid, fwid, tsid, twid, "
                        "ltype, conf, comment, usrname) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        new_wlinks,
                    )
                changes += len(new_wlinks)
            elif skipped:
                logger.info(
                    "%s: %d wlinks all unresolvable (%d skipped)",
                    name, len(old_wlinks), skipped,
                )

            if not dry_run and new_wlinks:
                live_conn.commit()
            live_conn.close()

    # --- slinks (essay only — story/dm slinks are already merged) ---
    if "slink" in old_tables and "essay" in name:
        old_slinks = old_conn.execute(
            "SELECT fsid, tsid, ltype, conf, comment FROM slink"
        ).fetchall()

        if old_slinks:
            f_formula = SID_FORMULAS[f_key]
            t_formula = SID_FORMULAS[t_key]

            live_conn = sqlite3.connect(str(live_link_db))
            existing_slinks = set()
            try:
                existing_slinks = {
                    (r[0], r[1])
                    for r in live_conn.execute("SELECT fsid, tsid FROM slink").fetchall()
                }
            except sqlite3.OperationalError:
                pass

            max_slid = 0
            try:
                r = live_conn.execute("SELECT COALESCE(MAX(slid), 0) FROM slink").fetchone()
                max_slid = r[0]
            except sqlite3.OperationalError:
                pass

            new_slinks = []
            for fsid, tsid, ltype, conf, comment in old_slinks:
                new_fsid = f_formula(fsid)
                new_tsid = t_formula(tsid)
                if (new_fsid, new_tsid) in existing_slinks:
                    continue
                max_slid += 1
                new_slinks.append(
                    (max_slid, new_fsid, new_tsid, ltype, conf, comment, None)
                )

            if new_slinks:
                logger.info(
                    "%s: %s %d slinks (%d already present)",
                    name, "would import" if dry_run else "importing",
                    len(new_slinks),
                    len(old_slinks) - len(new_slinks),
                )
                if not dry_run:
                    live_conn.executemany(
                        "INSERT INTO slink (slid, fsid, tsid, ltype, conf, "
                        "comment, usrname) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        new_slinks,
                    )
                changes += len(new_slinks)

            if not dry_run and new_slinks:
                live_conn.commit()
            live_conn.close()

    old_conn.close()
    return changes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Import cross-lingual concept and word links from old per-genre databases."
    )
    parser.add_argument(
        "--fix", action="store_true", help="Apply imports to local build/ copies",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would change",
    )
    args = parser.parse_args()

    if not (args.fix or args.dry_run):
        logger.error("Specify --fix or --dry-run")
        sys.exit(1)

    global _cache
    _cache = LiveDBCache()

    total = 0
    for job in LINK_JOBS:
        (name, link_db, f_cdb, t_cdb, f_key, t_key,
         live_link, f_live, t_live) = job
        total += import_links_for_job(
            name, link_db, f_cdb, t_cdb, f_key, t_key,
            live_link, f_live, t_live,
            dry_run=args.dry_run,
        )

    action = "would import" if args.dry_run else "imported"
    logger.info("Total: %s %d link(s)", action, total)


if __name__ == "__main__":
    main()
