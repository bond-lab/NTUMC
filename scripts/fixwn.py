#!/usr/bin/env python3
"""Fix validation issues in wn-ntumc.db.

Addresses three categories of problems found during wordnet validation:

  W502  Self-loop synlinks (synset1 == synset2) — deleted
  W501  POS-mismatch hypernyms — per-case fixes (delete link, rename
        synset, delete synset, merge senses, or leave as-is)
  DEF   Wrong definitions — exact-string replacements, duplicate deletion
  SENSE Wrong senses — deleted
  DEIX  Missing deixis links (dmnu/dmtu) from demonstratives to
        medial/proximal/distal/remote
  TWO   "of two" feature replaces dual for either/neither/both and the
        one-of-two pronouns; either split into universal and elective

Usage:
    fixwn.py WN_DB [--dry-run]
"""

import argparse
import sqlite3


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
    # 80001711-z removed: renamed to 80001711-x (non-referential)
    "77000088-r",   # 那样 (manner pronoun) → manner
    "80000664-x",   # good evening → greeting
    "80002274-x",   # lol → webspeak
}

# Rename synset IDs (fix POS in both column and ID)
RENAME_SYNSET = {
    # old_id: new_id
    "90000406-n": "90000406-a",  # rocking — def: "energetic, favourable"
    "80002595-n": "80002595-v",  # suikou (推敲する) — "to perfect a writing"
    "80002126-z": "80002126-p",  # in — "location, or position within" → adposition
    "80001711-z": "80001711-x",  # 们 — "plural suffix" → non-referential
    "80002491-z": "80002491-a",  # svůj — "own" → adnominal
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


# ── DEF: Wrong definitions ────────────────────────────────────────────

# (synset, lang, old_def, new_def)
FIX_DEF = [
    # Japanese a-series demonstratives are remote, not distal
    # (distal is for two-way systems: that, 那, itu)
    ("77000048-n", "eng",
     "3rd person, singular, masculine, informal, distal pronoun",
     "3rd person, singular, masculine, informal, remote pronoun"),  # あいつ
    ("77000059-n", "eng",
     "demonstratives, singular, distal pronoun",
     "demonstratives, singular, remote pronoun"),                   # あれ
    ("77000070-n", "eng",
     "entity, dual, formal, distal pronoun",
     "entity, of two, formal, remote pronoun"),                     # あちら
    # "dual" is number (a pair: we two); these choose from a set of two,
    # so they get the feature "of two" (domain Two, Jeretič et al. 2026)
    ("77000071-n", "eng",
     "entity, dual, formal, medial pronoun",
     "entity, of two, formal, medial pronoun"),                     # そちら
    ("77000072-n", "eng",
     "entity, dual, formal, proximal pronoun",
     "entity, of two, formal, proximal pronoun"),                   # こちら
    ("77000073-n", "eng",
     "entity, dual, informal, proximal pronoun",
     "entity, of two, informal, proximal pronoun"),                 # こっち
    ("77000074-n", "eng",
     "entity, dual, elective existential pronoun",
     "entity, of two, elective existential pronoun"),               # either
    ("77000076-a", "eng",
     "quantifier, dual universal",
     "quantifier, of two, universal"),                              # both
    ("77000076-n", "eng",
     "entity, dual, universal pronoun",
     "entity, of two, universal pronoun"),                          # both
    ("77000076-n", "eng",
     "pronoun, entity, dual; quantifier:  dual universal",
     "pronoun, entity, of two; quantifier: of two, universal"),     # both
    ("00524607-a", "eng",
     "entity, dual, negative pronoun",
     "entity, of two, negative pronoun"),                           # neither
    ("00524607-a", "eng",
     "quantifier, dual, negative",
     "quantifier, of two, negative"),                               # neither
    ("00524607-n", "eng",
     "pronoun, entity; quantifier: quantifier, dual, negative",
     "pronoun, entity; quantifier: quantifier, of two, negative"),  # neither
    # the either/neither pronouns are singular, like their determiners
    # (applied after the dual -> of two rows above)
    ("77000074-n", "eng",
     "entity, of two, elective existential pronoun",
     "entity, singular, of two, elective existential pronoun"),     # either
    ("00524607-n", "eng",
     "pronoun, entity; quantifier: quantifier, of two, negative",
     ("pronoun, entity, singular; quantifier: quantifier, of two, "
      "negative")),                                                 # neither
    # Indonesian is two-way adnominally (and Chinese two-way), so the
    # manner pronoun is distal, matching its existing link
    ("77000088-r", "eng",
     "manner, medial pronoun",
     "manner, distal pronoun"),                     # 那样, begitu, demikian
    ("77000088-n", "eng",
     "manner, medial pronoun",
     "manner, distal pronoun"),                     # (no senses)
]


def fix_defs(db, dry_run):
    """Replace definitions that exactly match a known-bad string."""
    n = 0
    for ss, lang, old, new in FIX_DEF:
        found = db.execute(
            "SELECT COUNT(*) FROM synset_def "
            "WHERE synset=? AND lang=? AND def=?", (ss, lang, old)
        ).fetchone()[0]
        if not found:
            print(f"    {ss}: already fixed or not found")
            continue
        print(f"    {ss}: {old!r} -> {new!r}")
        n += found
        if not dry_run:
            db.execute(
                "UPDATE synset_def SET def=? "
                "WHERE synset=? AND lang=? AND def=?", (new, ss, lang, old)
            )
    return n


# Duplicate definitions to delete: (synset, lang, sid)
DELETE_DEF = [
    ("77010001-a", "eng", 1),  # medial: same as sid 0 with a double space
]


def delete_defs(db, dry_run):
    """Delete duplicate definitions by synset, language and sid."""
    n = 0
    for ss, lang, sid in DELETE_DEF:
        found = db.execute(
            "SELECT def FROM synset_def WHERE synset=? AND lang=? AND sid=?",
            (ss, lang, sid),
        ).fetchone()
        if not found:
            print(f"    {ss} sid {sid}: already deleted or not found")
            continue
        print(f"    {ss} sid {sid}: delete {found[0]!r}")
        n += 1
        if not dry_run:
            db.execute(
                "DELETE FROM synset_def WHERE synset=? AND lang=? AND sid=?",
                (ss, lang, sid),
            )
    return n


# ── SENSE: Wrong senses ───────────────────────────────────────────────

# (synset, lang, lemma) senses to delete
DELETE_SENSE = [
    # 哪 'which' is interrogative (77000091-a), not distal 'that' (那)
    ("77000079-a", "cmn", "哪"),
]


def delete_senses(db, dry_run):
    """Delete senses that link a word to the wrong synset."""
    n = 0
    for ss, lang, lemma in DELETE_SENSE:
        rows = db.execute(
            "SELECT s.wordid FROM sense s JOIN word w USING (wordid) "
            "WHERE s.synset=? AND w.lang=? AND w.lemma=?", (ss, lang, lemma)
        ).fetchall()
        if not rows:
            print(f"    {ss} {lemma}: already deleted or not found")
            continue
        print(f"    {ss} {lemma}: delete sense")
        n += len(rows)
        if not dry_run:
            db.executemany(
                "DELETE FROM sense WHERE synset=? AND wordid=?",
                [(ss, wid) for (wid,) in rows],
            )
    return n


# ── DEIX: Missing deixis links ────────────────────────────────────────

MEDIAL, PROXIMAL, DISTAL, REMOTE = (
    "77010001-a", "77010002-a", "77010003-a", "77010004-a"
)

# Demonstrative synset -> deixis synset, following the definitions.
# Japanese is three-way (ko/so/a = proximal/medial/remote); English,
# Chinese, Czech and Indonesian (adnominally) are two-way (proximal/distal).
DEIXIS = {
    # medial: so-series
    "77000057-n": MEDIAL,    # それら
    "77000060-a": MEDIAL,    # その
    "77000060-n": MEDIAL,    # それ
    "77000071-n": MEDIAL,    # そちら
    "77000109-n": MEDIAL,    # そいつ
    "77000110-n": MEDIAL,    # そいつら
    "77000113-a": MEDIAL,    # そんな
    "77000113-r": MEDIAL,    # そんなに
    "77000115-n": MEDIAL,    # そっち
    "77000117-n": MEDIAL,    # そこ
    # proximal: ko-series, this/these, 这, ini
    "77000058-a": PROXIMAL,  # these, 这些, ini semua
    "77000058-n": PROXIMAL,  # these, これら
    "77000061-a": PROXIMAL,  # this
    "77000061-n": PROXIMAL,  # this, これ
    "77000072-n": PROXIMAL,  # こちら
    "77000073-n": PROXIMAL,  # こっち
    "77000075-a": PROXIMAL,  # この, 这, ini
    "77000075-n": PROXIMAL,  # これ, 这, ini
    "77000089-a": PROXIMAL,  # こんな, 这样
    "77000089-r": PROXIMAL,  # こんなに, begini
    "77000122-n": PROXIMAL,  # こいつ
    "77000123-n": PROXIMAL,  # こいつら
    # distal: that/those, 那, itu
    "77000079-a": DISTAL,    # that
    "77000079-n": DISTAL,    # that
    "77000080-a": DISTAL,    # 那, itu
    "77000080-n": DISTAL,    # 那, itu
    "77000082-a": DISTAL,    # those, 那些
    "77000082-n": DISTAL,    # those, 那些
    "77000088-r": DISTAL,    # 那样, begitu
    # remote: a-series, sana
    "77000048-n": REMOTE,    # あいつ
    "77000059-a": REMOTE,    # あの
    "77000059-n": REMOTE,    # あれ
    "77000070-n": REMOTE,    # あちら
    "77000081-n": REMOTE,    # あそこ, sana
    "77000108-n": REMOTE,    # あいつら
    "77000114-a": REMOTE,    # あんな
    "77000114-r": REMOTE,    # あんなに
    "77000116-n": REMOTE,    # あっち
}


def _add_link(db, s1, link, s2, dry_run):
    """Add a synlink unless it already exists; return 1 if added."""
    if db.execute(
        "SELECT 1 FROM synlink WHERE synset1=? AND synset2=? AND link=?",
        (s1, s2, link),
    ).fetchone():
        return 0
    print(f"    add: {s1} --{link}--> {s2}")
    if not dry_run:
        db.execute(
            "INSERT INTO synlink (synset1, synset2, link, src) "
            "VALUES (?, ?, ?, 'pron')", (s1, s2, link),
        )
    return 1


def fix_deixis(db, dry_run):
    """Link each demonstrative to its deixis synset (dmnu + reverse dmtu)."""
    n = 0
    for ss, deix in DEIXIS.items():
        n += _add_link(db, ss, "dmnu", deix, dry_run)
        n += _add_link(db, deix, "dmtu", ss, dry_run)
    print(f"  {n} links {'to add' if dry_run else 'added'}.")
    return n


# ── TWO: "of two" feature and the two kinds of either ────────────────

TWO = "77010009-n"
DUAL = "02183135-a"
QUANTIFIER, SINGULAR = "06302381-n", "06299916-n"
EITHER_UNIV, EITHER_ELEC = "77000141-a", "77000142-a"

# New synsets: (synset, name, definition)
NEW_SYNSETS = [
    (TWO, "of two",
     "used of a word that chooses from or quantifies over a set of two"),
    # universal either (on either side = each of the two): it is to
    # each (02269635-a) what both is to all
    (EITHER_UNIV, "either", "quantifier, singular, of two, universal"),
    # elective either (take either road): one of two, any one
    (EITHER_ELEC, "either", "quantifier, singular, of two, elective existential"),
]

# Words that choose from a set of two
OF_TWO = [
    "77000070-n", "77000071-n", "77000072-n",  # あちら, そちら, こちら
    "77000073-n", "77000115-n", "77000116-n",  # こっち, そっち, あっち
    "77000065-n", "77000066-n",                # どちら, どっち
    "77000074-n", EITHER_UNIV, EITHER_ELEC,    # either
    "00524607-n", "00524607-a",                # neither
    "77000076-n", "77000076-a",                # both
]

# Links to delete: (synset1, link, synset2), each with its reverse
DELETE_TWO_LINKS = [
    # dual is number, not one-of-two
    ("77000074-n", "dmnu", DUAL),
    ("77000076-n", "dmnu", DUAL),
    ("77000076-a", "dmnu", DUAL),
    ("00524607-a", "dmnu", DUAL),
    # pronoun either now has its own determiner, not any
    ("77000074-n", "hasq", "02267686-a"),
]
REVERSE = {"dmnu": "dmtu", "hasq": "qant"}

# Links to add, each with its reverse
ADD_TWO_LINKS = [(ss, "dmnu", TWO) for ss in OF_TWO] + [
    (EITHER_UNIV, "dmnu", QUANTIFIER),
    (EITHER_UNIV, "dmnu", SINGULAR),
    (EITHER_ELEC, "dmnu", QUANTIFIER),
    (EITHER_ELEC, "dmnu", SINGULAR),
    ("77000074-n", "hasq", EITHER_ELEC),
    ("77000074-n", "dmnu", SINGULAR),
    ("00524607-n", "dmnu", SINGULAR),
]

# Move the English either sense from both (77000076-a) to universal either
MOVE_SENSE = [("77000076-a", EITHER_UNIV, "eng", "either")]
# New senses: (synset, lang, lemma, pos)
NEW_SENSES = [(TWO, "eng", "of two", "n"),
              (EITHER_ELEC, "eng", "either", "a")]


def _add_synset(db, ss, name, definition, dry_run):
    """Add a synset with one English definition unless it exists."""
    if db.execute("SELECT 1 FROM synset WHERE synset=?", (ss,)).fetchone():
        return 0
    print(f"    add synset: {ss} {name!r}: {definition!r}")
    if not dry_run:
        db.execute(
            "INSERT INTO synset (synset, pos, name, src) "
            "VALUES (?, ?, ?, 'pron')", (ss, ss[-1], name),
        )
        db.execute(
            "INSERT INTO synset_def (synset, lang, def, sid) "
            "VALUES (?, 'eng', ?, 0)", (ss, definition),
        )
    return 1


def _wordid(db, lang, lemma, pos, dry_run):
    """Return the wordid for a lemma, adding the word if it is missing."""
    row = db.execute(
        "SELECT wordid FROM word WHERE lang=? AND lemma=? AND pos=?",
        (lang, lemma, pos),
    ).fetchone()
    if row:
        return row[0]
    print(f"    add word: {lemma!r} ({lang}, {pos})")
    if dry_run:
        return None
    return db.execute(
        "INSERT INTO word (lang, lemma, pos) VALUES (?, ?, ?)",
        (lang, lemma, pos),
    ).lastrowid


def _add_sense(db, ss, lang, lemma, pos, dry_run):
    """Add a sense unless the word already has one in this synset."""
    if db.execute(
        "SELECT 1 FROM sense s JOIN word w USING (wordid) "
        "WHERE s.synset=? AND w.lang=? AND w.lemma=?", (ss, lang, lemma)
    ).fetchone():
        return 0
    wid = _wordid(db, lang, lemma, pos, dry_run)
    print(f"    add sense: {ss} {lemma}")
    if not dry_run:
        db.execute(
            "INSERT INTO sense (synset, wordid, lang, src, confidence) "
            "VALUES (?, ?, ?, 'pron', 1.0)", (ss, wid, lang),
        )
    return 1


def _move_sense(db, old, new, lang, lemma, dry_run):
    """Move a word's sense from one synset to another."""
    row = db.execute(
        "SELECT s.wordid FROM sense s JOIN word w USING (wordid) "
        "WHERE s.synset=? AND w.lang=? AND w.lemma=?", (old, lang, lemma)
    ).fetchone()
    if not row:
        print(f"    {old} {lemma}: already moved or not found")
        return 0
    print(f"    move sense: {lemma} {old} -> {new}")
    if not dry_run:
        db.execute(
            "UPDATE sense SET synset=? WHERE synset=? AND wordid=?",
            (new, old, row[0]),
        )
    return 1


def fix_two(db, dry_run):
    """Add the "of two" feature and split either into universal/elective."""
    n = 0
    for ss, name, definition in NEW_SYNSETS:
        n += _add_synset(db, ss, name, definition, dry_run)
    for ss, lang, lemma, pos in NEW_SENSES:
        n += _add_sense(db, ss, lang, lemma, pos, dry_run)
    for old, new, lang, lemma in MOVE_SENSE:
        n += _move_sense(db, old, new, lang, lemma, dry_run)
    for s1, link, s2 in DELETE_TWO_LINKS:
        for a, lk, b in ((s1, link, s2), (s2, REVERSE[link], s1)):
            if db.execute(
                "SELECT 1 FROM synlink WHERE synset1=? AND link=? "
                "AND synset2=?", (a, lk, b)
            ).fetchone():
                print(f"    delete: {a} --{lk}--> {b}")
                n += 1
                if not dry_run:
                    db.execute(
                        "DELETE FROM synlink WHERE synset1=? AND link=? "
                        "AND synset2=?", (a, lk, b)
                    )
    for s1, link, s2 in ADD_TWO_LINKS:
        n += _add_link(db, s1, link, s2, dry_run)
        n += _add_link(db, s2, REVERSE[link], s1, dry_run)
    return n


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

    triggers = []
    if not args.dry_run:
        triggers = db.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
        ).fetchall()
        if triggers:
            print(f"Dropping {len(triggers)} triggers...")
            for name, _ in triggers:
                db.execute(f"DROP TRIGGER [{name}]")

    print("--- W502: Self-loops ---")
    fix_self_loops(db, args.dry_run)
    print()

    print("--- W501: POS-mismatch hypernyms ---")
    fix_pos_mismatches(db, args.dry_run)
    print()

    print("--- DEF: Wrong definitions ---")
    fix_defs(db, args.dry_run)
    delete_defs(db, args.dry_run)
    print()

    print("--- SENSE: Wrong senses ---")
    delete_senses(db, args.dry_run)
    print()

    print("--- DEIX: Missing deixis links ---")
    fix_deixis(db, args.dry_run)
    print()

    print("--- TWO: of-two feature, either split ---")
    fix_two(db, args.dry_run)
    print()

    if not args.dry_run:
        if triggers:
            print(f"Restoring {len(triggers)} triggers...")
            for _, sql in triggers:
                if sql:
                    db.executescript(sql)
        db.commit()
        print("Changes committed.")
    else:
        print("Dry run complete — no changes made.")

    db.close()


if __name__ == "__main__":
    main()
