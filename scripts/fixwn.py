#!/usr/bin/env python3
"""Fix validation issues in wn-ntumc.db.

Addresses three categories of problems found during wordnet validation:

  W502  Self-loop synlinks (synset1 == synset2) — deleted
  W501  POS-mismatch hypernyms — per-case fixes (delete link, rename
        synset, delete synset, merge senses, or leave as-is)

Usage:
    fixwn.py WN_DB [--dry-run]
"""

import argparse
import sqlite3
import sys


def _rename_synset(db, old, new, dry_run):
    """Rename a synset ID across all tables."""
    print(f"    rename synset: {old} -> {new}")
    if dry_run:
        return
    # Main tables
    db.execute("UPDATE synset SET synset=? WHERE synset=?", (new, old))
    db.execute("UPDATE synset_def SET synset=? WHERE synset=?", (new, old))
    db.execute("UPDATE synset_ex SET synset=? WHERE synset=?", (new, old))
    db.execute("UPDATE sense SET synset=? WHERE synset=?", (new, old))
    db.execute(
        "UPDATE synlink SET synset1=? WHERE synset1=?", (new, old)
    )
    db.execute(
        "UPDATE synlink SET synset2=? WHERE synset2=?", (new, old)
    )
    # Optional tables (may not have rows)
    for tbl in ("synset_comment", "xlink", "xlinks", "core"):
        try:
            db.execute(f"UPDATE {tbl} SET synset=? WHERE synset=?",
                       (new, old))
        except sqlite3.OperationalError:
            pass
    for tbl in ("ancestor", "senslink", "syselink"):
        try:
            db.execute(f"UPDATE {tbl} SET synset1=? WHERE synset1=?",
                       (new, old))
            db.execute(f"UPDATE {tbl} SET synset2=? WHERE synset2=?",
                       (new, old))
        except sqlite3.OperationalError:
            pass


def _delete_synset(db, ss, dry_run):
    """Delete a synset and all its senses, definitions, examples, links."""
    name = db.execute(
        "SELECT name FROM synset WHERE synset=?", (ss,)
    ).fetchone()
    n_senses = db.execute(
        "SELECT COUNT(*) FROM sense WHERE synset=?", (ss,)
    ).fetchone()[0]
    print(f"    delete synset: {ss} ({name[0] if name else '?'}, "
          f"{n_senses} senses)")
    if dry_run:
        return
    db.execute("DELETE FROM sense WHERE synset=?", (ss,))
    db.execute("DELETE FROM synset WHERE synset=?", (ss,))
    db.execute("DELETE FROM synset_def WHERE synset=?", (ss,))
    db.execute("DELETE FROM synset_ex WHERE synset=?", (ss,))
    db.execute(
        "DELETE FROM synlink WHERE synset1=? OR synset2=?", (ss, ss)
    )
    for tbl in ("synset_comment", "xlink", "xlinks", "core"):
        try:
            db.execute(f"DELETE FROM {tbl} WHERE synset=?", (ss,))
        except sqlite3.OperationalError:
            pass


# ── W502: Self-loops ──────────────────────────────────────────────────

def fix_self_loops(db, dry_run):
    """Delete all synlink rows where synset1 == synset2."""
    rows = db.execute(
        "SELECT synset1, link FROM synlink WHERE synset1 = synset2"
    ).fetchall()
    if not rows:
        print("  No self-loops found.")
        return 0
    print(f"  Found {len(rows)} self-loop rows:")
    for s, link in rows:
        print(f"    {s} --{link}--> {s}")
    if not dry_run:
        db.execute("DELETE FROM synlink WHERE synset1 = synset2")
        print(f"  Deleted {len(rows)} self-loop rows.")
    return len(rows)


# ── W501: POS-mismatch hypernyms ─────────────────────────────────────

# Leave as-is: determiners, pronouns, grammatical words (intentional)
LEAVE_AS_IS = {
    "77000006-a", "77000024-a", "77000039-a", "77000043-a",  # poss. det.
    "77000050-a", "77000054-a", "77000107-a",
    "80000081-a", "80000142-a", "80000512-a", "80001281-a",
    "80001711-z",   # 们 (plural marker) → function_word
    "77000088-r",   # 那样 (manner pronoun) → manner
    "80000664-x",   # good evening → greeting
    "80002274-x",   # lol → webspeak
}

# Rename synset IDs (fix POS in both column and ID)
RENAME_SYNSET = {
    # old_id: new_id
    "90000406-n": "90000406-a",  # rocking — def: "energetic, favourable"
    "80002595-n": "80002595-v",  # suikou (推敲する) — "to perfect a writing"
}

# Delete bad hypernym links: (synset1, link, synset2)
DELETE_LINK = [
    # adj → verb
    ("01412721-a", "hype", "80001630-v"),   # farfetched → ring false
    ("01799457-a", "hype", "80001629-v"),   # plausible → ring true
    ("80001098-a", "hype", "00941990-v"),   # speak_with_reticence → talk
    ("80001098-a", "hype", "00963570-v"),   # speak_with_reticence → speak
    ("80002056-a", "hype", "01818235-v"),   # under someone's wing → encourage
    ("80002114-a", "hype", "02494356-v"),   # under lock and key → imprison
    # adj → noun
    ("02791483-a", "hype", "80002304-n"),   # sadomasochistic → BDSM
    ("80000228-a", "hype", "04433905-n"),   # two-tiered → tier
    ("80000531-a", "hype", "00026192-n"),   # moving sound → feeling
    ("80000554-a", "hype", "00262249-n"),   # glorious spectacle → decoration
    ("80000741-a", "hype", "14429382-n"),   # five-star → rating
    ("80000954-a", "hype", "04980008-n"),   # nauseating → olfactory_property
    ("80002049-a", "hype", "80000158-n"),   # mala → flavour
    ("80002049-a", "hype", "04992570-n"),   # mala → spiciness
    ("80002061-a", "hype", "04934546-n"),   # paste consistency → consistency
    ("80002142-a", "hype", "11515734-n"),   # 流光溢彩 → streamer
    ("80002266-a", "hype", "07823951-n"),   # curried → curry
    ("80002326-a", "hype", "04191943-n"),   # shelterless → shelter
    ("80002448-a", "hype", "09917593-n"),   # Desetiletý → child
    ("80001865-a", "hype", "00798245-n"),   # antifa → campaign
    # adj → adverb
    ("80000769-a", "hype", "00071601-r"),   # trans-island → around
    # noun → adj
    ("01163779-n", "hype", "80001932-a"),   # execution → capital
    ("80000351-n", "hype", "01037540-a"),   # foreign_good → foreign
    ("80000574-n", "hype", "02964782-a"),   # overseas_chinese → chinese
    ("80000284-n", "hype", "00559530-a"),   # free-range chicken → free-range
    # noun → verb
    ("80000221-n", "hype", "02367363-v"),   # from_the_beginning → act
    ("80000499-n", "hype", "01824339-v"),   # extravagant hope → wish
    ("80000503-n", "hype", "02750432-v"),   # ancient rhyme → rhyme
    ("80001790-n", "hype", "80001795-v"),   # crib → crack a crib
    ("80002238-n", "hype", "02608004-v"),   # neighbouring country → neighbor
    ("80002284-n", "hype", "01426397-v"),   # gangbang → sleep_together
    # noun → adverb
    ("80000196-n", "hype", "00051440-r"),   # square-towered → squarely
    # verb → adj
    ("00829107-v", "hype", "80002056-a"),   # teach → under someone's wing
    ("80001196-v", "hype", "02250691-a"),   # to_live_in_seclusion → recluse
    ("80001629-v", "hype", "01799457-a"),   # ring true → plausible
    ("80001934-v", "hype", "00957743-a"),   # fall foul of → cheating
    ("80001949-v", "hype", "80001865-a"),   # anti-japanese → antifa
    # verb → noun
    ("80000529-v", "hype", "07134850-n"),   # laugh and talk merrily → chat
    ("80000533-v", "hype", "00037396-n"),   # retreat after loss → action
    ("80000548-v", "hype", "00037396-n"),   # keep mum → action
    ("80000557-v", "hype", "00048374-n"),   # unexpected arrival → arrival
    ("80000813-v", "hype", "13764213-n"),   # recharge money → top-up
    ("80001730-v", "hype", "06746005-n"),   # reply letter → answer
    ("80002111-v", "hype", "07496463-n"),   # cut → distress
    ("80002233-v", "hype", "13550318-n"),   # 生育 → reproduction
    ("80002265-v", "hype", "09911226-n"),   # charing → charwoman
    ("80002293-v", "hype", "00148057-n"),   # tensioning → tightening
    ("80002319-v", "hype", "00406612-n"),   # refold → fold
    # adverb → adj/verb
    ("80000778-r", "hype", "01678729-a"),   # special trip → special
    ("80002232-r", "hype", "02270404-v"),   # 白白 → mooch
    # noun → x (wits' end)
    ("05124057-n", "hype", "80001792-x"),   # limit → wits' end
    ("05618056-n", "hype", "80001792-x"),   # brain → wits' end
    ("05622196-n", "hype", "80001792-x"),   # wits → wits' end
]

# Delete synsets entirely (compositional, not real concepts)
DELETE_SYNSET = [
    "90000428-n",  # late-night (compositional)
    "90000450-n",  # in-seat (compositional)
    "90000453-n",  # power-lunch (compositional)
    "90000405-n",  # jam (music, compositional)
]

# Merge: move senses from source synsets to target, then delete sources
# ocasní (ces) → caudal 02843816-a ("constituting or relating to a tail")
MERGE = [
    # (source_synsets, target_synset)
    (["80002581-a", "80002582-a", "80002583-a"], "02843816-a"),
]


def fix_pos_mismatches(db, dry_run):
    """Fix POS-mismatch hypernym issues."""
    # 1. Rename synset IDs
    renamed = 0
    for old_id, new_id in RENAME_SYNSET.items():
        exists = db.execute(
            "SELECT 1 FROM synset WHERE synset=?", (old_id,)
        ).fetchone()
        if exists:
            new_pos = new_id.rsplit("-", 1)[1]
            _rename_synset(db, old_id, new_id, dry_run)
            if not dry_run:
                db.execute(
                    "UPDATE synset SET pos=? WHERE synset=?", (new_pos, new_id)
                )
            renamed += 1
    print(f"  Renamed {renamed} synsets.")

    # 2. Delete bad hypernym links (and their reverses)
    deleted_links = 0
    for s1, link, s2 in DELETE_LINK:
        exists = db.execute(
            "SELECT 1 FROM synlink WHERE synset1=? AND link=? AND synset2=?",
            (s1, link, s2),
        ).fetchone()
        if exists:
            print(f"    delete link: {s1} --{link}--> {s2}")
            if not dry_run:
                db.execute(
                    "DELETE FROM synlink "
                    "WHERE synset1=? AND link=? AND synset2=?",
                    (s1, link, s2),
                )
                rev = {"hype": "hypo", "hypo": "hype"}.get(link)
                if rev:
                    db.execute(
                        "DELETE FROM synlink "
                        "WHERE synset1=? AND link=? AND synset2=?",
                        (s2, rev, s1),
                    )
            deleted_links += 1
    print(f"  Deleted {deleted_links} bad hypernym links.")

    # 3. Delete compositional synsets
    deleted_ss = 0
    for ss in DELETE_SYNSET:
        exists = db.execute(
            "SELECT 1 FROM synset WHERE synset=?", (ss,)
        ).fetchone()
        if exists:
            _delete_synset(db, ss, dry_run)
            deleted_ss += 1
    print(f"  Deleted {deleted_ss} compositional synsets.")

    # 4. Merge duplicate synsets
    merged = 0
    for sources, target in MERGE:
        target_exists = db.execute(
            "SELECT name FROM synset WHERE synset=?", (target,)
        ).fetchone()
        if not target_exists:
            print(f"    WARNING: merge target {target} not found, skipping")
            continue
        for src in sources:
            src_row = db.execute(
                "SELECT name FROM synset WHERE synset=?", (src,)
            ).fetchone()
            if not src_row:
                continue
            # Get senses to move
            senses = db.execute(
                "SELECT wordid FROM sense WHERE synset=?", (src,)
            ).fetchall()
            # Check if sense already exists in target
            for (wid,) in senses:
                already = db.execute(
                    "SELECT 1 FROM sense WHERE synset=? AND wordid=?",
                    (target, wid),
                ).fetchone()
                if already:
                    print(f"    merge {src} -> {target}: "
                          f"wordid {wid} already in target, skip sense")
                else:
                    print(f"    merge {src} -> {target}: "
                          f"move wordid {wid}")
                    if not dry_run:
                        db.execute(
                            "UPDATE sense SET synset=? "
                            "WHERE synset=? AND wordid=?",
                            (target, src, wid),
                        )
            _delete_synset(db, src, dry_run)
            merged += 1
    print(f"  Merged {merged} synsets.")

    skipped = len(LEAVE_AS_IS)
    print(f"  Left as-is: {skipped} determiners/pronouns/grammatical words.")


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fix validation issues in wn-ntumc.db"
    )
    parser.add_argument("db", help="Path to wn-ntumc.db")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without modifying the database",
    )
    args = parser.parse_args()

    db = sqlite3.connect(args.db)
    mode = "DRY RUN" if args.dry_run else "APPLYING"
    print(f"=== fixwn.py ({mode}) ===\n")

    print("--- W502: Self-loops ---")
    fix_self_loops(db, args.dry_run)
    print()

    print("--- W501: POS-mismatch hypernyms ---")
    fix_pos_mismatches(db, args.dry_run)
    print()

    if not args.dry_run:
        db.commit()
        print("Changes committed.")
    else:
        print("Dry run complete — no changes made.")

    db.close()


if __name__ == "__main__":
    main()
