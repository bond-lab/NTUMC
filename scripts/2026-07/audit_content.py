#!/usr/bin/env python3
"""Content-level verification of renumbering-affected differences.

Checks that rows whose keys changed (sid/wid/cid renumbering) still exist
by content, and lists the small numbers of genuinely deleted rows so each
can be matched to a documented fix.
"""

import sqlite3
from collections import Counter
from pathlib import Path

SCRATCH = Path("/tmp/claude-1000/-home-bond-git-NTUMC/"
               "f6318767-d75a-4af6-9ca3-32719438f56d/scratchpad")
PRISTINE = SCRATCH / "pristine"
BUILD = Path("/home/bond/git/NTUMC/build")


def attach(lang: str) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.execute(f"ATTACH '{PRISTINE / (lang + '.db')}' AS p")
    con.execute(f"ATTACH '{BUILD / (lang + '.db')}' AS c")
    return con


def multiset_lost(con: sqlite3.Connection, sql_p: str, sql_c: str) -> Counter:
    """Items in pristine-multiset not covered by current-multiset."""
    mp = Counter(tuple(r) for r in con.execute(sql_p))
    mc = Counter(tuple(r) for r in con.execute(sql_c))
    return mp - mc


def show(counter: Counter, label: str, limit: int = 15) -> None:
    total = sum(counter.values())
    print(f"  {label}: {total} lost")
    for item, n in list(counter.items())[:limit]:
        print(f"    {n}x {item}")


print("=== cmn: 14 lost sids — does their text survive elsewhere? ===")
con = attach("cmn")
rows = con.execute(
    "SELECT p.sent.sid, p.sent.sent FROM p.sent "
    "WHERE p.sent.sid NOT IN (SELECT sid FROM c.sent)").fetchall()
for sid, text in rows:
    n = con.execute("SELECT COUNT(*) FROM c.sent WHERE sent = ?",
                    (text,)).fetchone()[0]
    status = f"found {n}x" if n else "*** TEXT GONE ***"
    print(f"  sid {sid}: {status}  {text[:40]!r}")

print("\n=== cmn: concept content (sent-text, clemma, tag) multiset ===")
lost = multiset_lost(
    con,
    "SELECT s.sent, c2.clemma, c2.tag FROM p.concept c2 "
    "JOIN p.sent s ON s.sid = c2.sid",
    "SELECT s.sent, c2.clemma, c2.tag FROM c.concept c2 "
    "JOIN c.sent s ON s.sid = c2.sid")
show(lost, "cmn concepts lost by content")

print("\n=== cmn: word content (sent-text, surface) multiset ===")
lost = multiset_lost(
    con,
    "SELECT s.sent, w.word FROM p.word w JOIN p.sent s ON s.sid = w.sid",
    "SELECT s.sent, w.word FROM c.word w JOIN c.sent s ON s.sid = w.sid")
show(lost, "cmn words lost by content")
con.close()

print("\n=== jpn: word content per sid (sids are stable) ===")
con = attach("jpn")
lost = multiset_lost(
    con,
    "SELECT sid, word, lemma, pos FROM p.word",
    "SELECT sid, word, lemma, pos FROM c.word")
show(lost, "jpn words lost by content")
lost = multiset_lost(
    con,
    "SELECT sid, clemma, tag FROM p.concept",
    "SELECT sid, clemma, tag FROM c.concept")
show(lost, "jpn concepts lost by content")
# cwl by content: (sid, clemma, word-surface)
lost = multiset_lost(
    con,
    "SELECT l.sid, con2.clemma, w.word FROM p.cwl l "
    "JOIN p.concept con2 ON con2.sid=l.sid AND con2.cid=l.cid "
    "JOIN p.word w ON w.sid=l.sid AND w.wid=l.wid",
    "SELECT l.sid, con2.clemma, w.word FROM c.cwl l "
    "JOIN c.concept con2 ON con2.sid=l.sid AND con2.cid=l.cid "
    "JOIN c.word w ON w.sid=l.sid AND w.wid=l.wid")
show(lost, "jpn cwl links lost by content")
con.close()

print("\n=== eng: the 13 deleted concept keys ===")
con = attach("eng")
for row in con.execute(
        "SELECT p.concept.sid, p.concept.cid, p.concept.clemma, "
        "p.concept.tag FROM p.concept "
        "LEFT JOIN c.concept ON c.concept.sid=p.concept.sid "
        "AND c.concept.cid=p.concept.cid WHERE c.concept.sid IS NULL"):
    print(f"  {row}")
print("\n=== eng: the 68 deleted cwl rows — were they orphans in pristine? ===")
n_orphan = con.execute(
    "SELECT COUNT(*) FROM (SELECT l.sid, l.cid, l.wid FROM p.cwl l "
    "EXCEPT SELECT sid, cid, wid FROM c.cwl) dead "
    "LEFT JOIN p.concept pc ON pc.sid=dead.sid AND pc.cid=dead.cid "
    "WHERE pc.sid IS NULL").fetchone()[0]
print(f"  orphaned (no matching concept in pristine): {n_orphan} / 68")
con.close()

print("\n=== ces: the 14 deleted concept keys ===")
con = attach("ces")
for row in con.execute(
        "SELECT p.concept.sid, p.concept.cid, p.concept.clemma, "
        "p.concept.tag FROM p.concept "
        "LEFT JOIN c.concept ON c.concept.sid=p.concept.sid "
        "AND c.concept.cid=p.concept.cid WHERE c.concept.sid IS NULL"):
    print(f"  {row}")
lost = multiset_lost(
    con,
    "SELECT sid, clemma, tag FROM p.concept",
    "SELECT sid, clemma, tag FROM c.concept")
show(lost, "ces concepts lost by content")
con.close()

print("\n=== ind: deleted concept + cwl analysis ===")
con = attach("ind")
for row in con.execute(
        "SELECT p.concept.sid, p.concept.cid, p.concept.clemma, "
        "p.concept.tag FROM p.concept "
        "LEFT JOIN c.concept ON c.concept.sid=p.concept.sid "
        "AND c.concept.cid=p.concept.cid WHERE c.concept.sid IS NULL"):
    print(f"  lost concept: {row}")
# of the 638 lost cwl keys, how many are same (sid,cid) remapped to new wid,
# how many were orphans, how many gone entirely?
remapped = con.execute(
    "SELECT COUNT(*) FROM (SELECT l.sid, l.cid, l.wid FROM p.cwl l "
    "EXCEPT SELECT sid, cid, wid FROM c.cwl) dead "
    "WHERE EXISTS (SELECT 1 FROM c.cwl cc WHERE cc.sid=dead.sid "
    "AND cc.cid=dead.cid)").fetchone()[0]
orphan = con.execute(
    "SELECT COUNT(*) FROM (SELECT l.sid, l.cid, l.wid FROM p.cwl l "
    "EXCEPT SELECT sid, cid, wid FROM c.cwl) dead "
    "LEFT JOIN p.concept pc ON pc.sid=dead.sid AND pc.cid=dead.cid "
    "WHERE pc.sid IS NULL").fetchone()[0]
print(f"  lost cwl keys where (sid,cid) still linked (wid remap): {remapped}")
print(f"  lost cwl keys that were orphans in pristine: {orphan}")
con.close()

print("\n=== eng: word content check (essay merge aside, sids stable) ===")
con = attach("eng")
lost = multiset_lost(
    con,
    "SELECT sid, word FROM p.word",
    "SELECT sid, word FROM c.word")
show(lost, "eng words lost by content", limit=10)
con.close()
