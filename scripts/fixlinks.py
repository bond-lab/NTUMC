#!/usr/bin/env python3
"""Fix synlink errors and list orphan synsets in wn-ntumc.db.

Usage: fixlinks.py WN_DB [--dry-run]

How to fix on compling
$ scp compling.upol.cz:/var/www/ntumc/db/wn-ntumc.db /tmp/wn-ntumc.db
$ .venv/bin/python scripts/fixlinks.py /tmp/wn-ntumc.db
$ scp /tmp/wn-ntumc.db compling.upol.cz:/var/www/ntumc/db/wn-ntumc.db

Fixes:
- W403: Remove duplicate synlink rows
- W404: Add missing reverse relations (except enta/caus, handled in getwn.py)
- Lists orphan synsets (no senses in any language) and optionally deletes them
"""

import argparse
import sqlite3

# Map of DB link codes to their reverse codes.
# enta and caus excluded — reverse handled at export time in getwn.py.
DB_REVERSE = {
    "hype": "hypo",  "hypo": "hype",
    "inst": "hasi",  "hasi": "inst",
    "mprt": "hprt",  "hprt": "mprt",
    "msub": "hsub",  "hsub": "msub",
    "mmem": "hmem",  "hmem": "mmem",
    "dmnc": "dmtc",  "dmtc": "dmnc",
    "dmnr": "dmtr",  "dmtr": "dmnr",
    "dmnu": "dmtu",  "dmtu": "dmnu",
    "qant": "hasq",  "hasq": "qant",
    # Symmetric (reverse is the same code, with swapped synsets)
    "ants": "ants",  "sim": "sim",
    "also": "also",  "attr": "attr",
    "eqls": "eqls",
}


def fix_duplicates(con, dry_run=False):
    """W403: Delete duplicate synlink rows, keeping one copy."""
    c = con.cursor()
    c.execute("""
        SELECT synset1, synset2, link, COUNT(*) as cnt
        FROM synlink
        GROUP BY synset1, synset2, link
        HAVING cnt > 1
    """)
    dupes = c.fetchall()
    if not dupes:
        print("  W403: no duplicates found")
        return 0

    total = sum(cnt - 1 for _, _, _, cnt in dupes)
    print(f"  W403: {len(dupes)} duplicate groups, {total} rows to delete")

    if dry_run:
        for s1, s2, link, cnt in dupes[:10]:
            print(f"    {s1} -> {s2} ({link}) x{cnt}")
        if len(dupes) > 10:
            print(f"    ... and {len(dupes) - 10} more")
        return total

    c.execute("""
        DELETE FROM synlink WHERE rowid NOT IN (
            SELECT MIN(rowid) FROM synlink GROUP BY synset1, synset2, link
        )
    """)
    con.commit()
    print(f"  W403: deleted {total} duplicate rows")
    return total


def fix_reverse_links(con, dry_run=False):
    """W404: Add missing reverse relations."""
    c = con.cursor()

    missing = []
    for link, rev in DB_REVERSE.items():
        c.execute("""
            SELECT s.synset1, s.synset2
            FROM synlink s
            WHERE s.link = ?
              AND NOT EXISTS (
                SELECT 1 FROM synlink r
                WHERE r.synset1 = s.synset2
                  AND r.synset2 = s.synset1
                  AND r.link = ?
              )
        """, (link, rev))
        for s1, s2 in c.fetchall():
            missing.append((s2, s1, rev))

    if not missing:
        print("  W404: no missing reverse links")
        return 0

    # Count by link type
    by_type = {}
    for _, _, link in missing:
        by_type[link] = by_type.get(link, 0) + 1

    print(f"  W404: {len(missing)} missing reverse links to add")
    for link, cnt in sorted(by_type.items()):
        print(f"    {link}: {cnt}")

    if dry_run:
        return len(missing)

    c.executemany(
        "INSERT INTO synlink (synset1, synset2, link, src, usr)"
        " VALUES (?, ?, ?, 'fix', 'fixlinks')",
        missing,
    )
    con.commit()
    print(f"  W404: inserted {len(missing)} reverse links")
    return len(missing)


def list_orphan_synsets(con, dry_run=False):
    """Find and optionally delete synsets with no senses in any language."""
    c = con.cursor()
    c.execute("""
        SELECT s.synset, s.pos, s.name,
               (SELECT COUNT(*) FROM synset_def d
                WHERE d.synset = s.synset) AS ndefs,
               (SELECT COUNT(*) FROM synlink l
                WHERE l.synset1 = s.synset
                   OR l.synset2 = s.synset) AS nlinks
        FROM synset s
        WHERE NOT EXISTS (
            SELECT 1 FROM sense se WHERE se.synset = s.synset
        )
        ORDER BY s.synset
    """)
    orphans = c.fetchall()

    if not orphans:
        print("  Orphans: none found")
        return 0

    print(f"\n  Orphan synsets ({len(orphans)} with no senses):")
    print(f"  {'synset':<16} {'pos':<4} {'name':<40} {'defs':>4} {'links':>5}")
    print(f"  {'-'*16} {'-'*4} {'-'*40} {'-'*4} {'-'*5}")
    for synset, pos, name, ndefs, nlinks in orphans:
        print(
            f"  {synset:<16} {pos or '?':<4} {(name or '')[:40]:<40}"
            f" {ndefs:>4} {nlinks:>5}"
        )

    if dry_run:
        print(f"\n  Dry run: would delete {len(orphans)} orphan synsets")
        return len(orphans)

    print(
        f"\n  Delete all {len(orphans)} orphan synsets? [y/N] ",
        end="", flush=True,
    )
    answer = input().strip().lower()
    if answer != "y":
        print("  Skipped orphan deletion")
        return 0

    synset_ids = [row[0] for row in orphans]
    ph = ",".join("?" * len(synset_ids))

    c.execute(
        f"DELETE FROM synlink WHERE synset1 IN ({ph}) OR synset2 IN ({ph})",
        synset_ids + synset_ids,
    )
    c.execute(f"DELETE FROM synset_ex WHERE synset IN ({ph})", synset_ids)
    c.execute(f"DELETE FROM synset_def WHERE synset IN ({ph})", synset_ids)
    c.execute(f"DELETE FROM synset WHERE synset IN ({ph})", synset_ids)
    con.commit()
    print(f"  Deleted {len(orphans)} orphan synsets and related data")
    return len(orphans)


def main():
    parser = argparse.ArgumentParser(
        description="Fix synlink errors and list orphan synsets in wn-ntumc.db",
    )
    parser.add_argument("db", help="Path to wn-ntumc.db")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview changes without modifying the database",
    )
    args = parser.parse_args()

    con = sqlite3.connect(args.db)

    if args.dry_run:
        print("=== DRY RUN (no changes will be made) ===\n")

    fix_duplicates(con, args.dry_run)
    fix_reverse_links(con, args.dry_run)
    list_orphan_synsets(con, args.dry_run)

    con.close()


if __name__ == "__main__":
    main()
