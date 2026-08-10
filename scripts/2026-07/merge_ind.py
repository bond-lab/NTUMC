#!/usr/bin/env python3
"""Merge Indonesian data from the 2016 snapshot into raw/ind.db.

The raw/ind.db (from the server) is a snapshot from ~Jan 2016.
The 2016-11-30/ind.db has ~8 months of additional annotation work.
This script brings raw up to date by:
  1. Filling 4,626 missing tags (empty in raw, tagged in 2016)
  2. Updating 144 conflicting tags (2016 is newer per concept_log)
  3. Inserting 82 concept rows only in 2016
  4. Inserting 33 word rows only in 2016
  5. Updating 368 word rows that differ (2016 is newer per word_log)
  6. Inserting 371 cwl rows only in 2016
  7. Inserting 256 sentiment rows only in 2016
  8. Merging concept_log history from 2016
"""

import shutil
import sqlite3
import sys
from pathlib import Path

RAW = Path("raw/ind.db")
OLD = Path("/home/bond/work/ntu-mc/2016-11-30/ind.db")
BACKUP = RAW.with_suffix(".db.bak")


def main():
    if not RAW.exists():
        sys.exit(f"ERROR: {RAW} not found")
    if not OLD.exists():
        sys.exit(f"ERROR: {OLD} not found")

    shutil.copy2(RAW, BACKUP)
    print(f"Backed up {RAW} -> {BACKUP}")

    conn = sqlite3.connect(RAW)
    conn.execute(f"ATTACH '{OLD}' AS old")

    counts = {}

    # 1. Fill missing tags (raw empty, 2016 has value)
    cur = conn.execute("""
        UPDATE concept SET
            tag = (SELECT o.tag FROM old.concept o
                   WHERE o.sid = concept.sid AND o.cid = concept.cid),
            clemma = (SELECT o.clemma FROM old.concept o
                      WHERE o.sid = concept.sid AND o.cid = concept.cid),
            usrname = (SELECT o.usrname FROM old.concept o
                       WHERE o.sid = concept.sid AND o.cid = concept.cid)
        WHERE (tag IS NULL OR tag = '')
          AND EXISTS (
            SELECT 1 FROM old.concept o
            WHERE o.sid = concept.sid AND o.cid = concept.cid
              AND o.tag IS NOT NULL AND o.tag != ''
          )
    """)
    counts["tags filled"] = cur.rowcount
    print(f"  Tags filled (empty->tagged): {cur.rowcount}")

    # 2. Update conflicting tags (both have values, 2016 is newer)
    cur = conn.execute("""
        UPDATE concept SET
            tag = (SELECT o.tag FROM old.concept o
                   WHERE o.sid = concept.sid AND o.cid = concept.cid),
            usrname = (SELECT o.usrname FROM old.concept o
                       WHERE o.sid = concept.sid AND o.cid = concept.cid)
        WHERE tag IS NOT NULL AND tag != ''
          AND EXISTS (
            SELECT 1 FROM old.concept o
            WHERE o.sid = concept.sid AND o.cid = concept.cid
              AND o.tag IS NOT NULL AND o.tag != ''
              AND o.tag != concept.tag
          )
    """)
    counts["tags updated"] = cur.rowcount
    print(f"  Tags updated (conflict->2016): {cur.rowcount}")

    # 3. Insert concept rows only in 2016
    cur = conn.execute("""
        INSERT INTO concept (sid, cid, clemma, tag, tags, comment, usrname, ntag)
        SELECT o.sid, o.cid, o.clemma, o.tag, o.tags, o.comment, o.usrname, o.ntag
        FROM old.concept o
        WHERE NOT EXISTS (
            SELECT 1 FROM concept c WHERE c.sid = o.sid AND c.cid = o.cid
        )
    """)
    counts["concepts inserted"] = cur.rowcount
    print(f"  Concepts inserted (2016-only): {cur.rowcount}")

    # 4. Insert word rows only in 2016
    cur = conn.execute("""
        INSERT INTO word (sid, wid, word, pos, lemma, cfrom, cto, comment, usrname)
        SELECT o.sid, o.wid, o.word, o.pos, o.lemma, o.cfrom, o.cto, o.comment, o.usrname
        FROM old.word o
        WHERE NOT EXISTS (
            SELECT 1 FROM word w WHERE w.sid = o.sid AND w.wid = o.wid
        )
    """)
    counts["words inserted"] = cur.rowcount
    print(f"  Words inserted (2016-only): {cur.rowcount}")

    # 5. Update differing word rows (2016 is newer per word_log)
    cur = conn.execute("""
        UPDATE word SET
            word = (SELECT o.word FROM old.word o
                    WHERE o.sid = word.sid AND o.wid = word.wid),
            pos = (SELECT o.pos FROM old.word o
                   WHERE o.sid = word.sid AND o.wid = word.wid),
            lemma = (SELECT o.lemma FROM old.word o
                     WHERE o.sid = word.sid AND o.wid = word.wid),
            cfrom = (SELECT o.cfrom FROM old.word o
                     WHERE o.sid = word.sid AND o.wid = word.wid),
            cto = (SELECT o.cto FROM old.word o
                   WHERE o.sid = word.sid AND o.wid = word.wid),
            usrname = (SELECT o.usrname FROM old.word o
                       WHERE o.sid = word.sid AND o.wid = word.wid)
        WHERE EXISTS (
            SELECT 1 FROM old.word o
            WHERE o.sid = word.sid AND o.wid = word.wid
              AND (COALESCE(o.word,'') != COALESCE(word.word,'')
                OR COALESCE(o.pos,'') != COALESCE(word.pos,'')
                OR COALESCE(o.lemma,'') != COALESCE(word.lemma,''))
        )
    """)
    counts["words updated"] = cur.rowcount
    print(f"  Words updated (differ->2016): {cur.rowcount}")

    # 6. Insert cwl rows only in 2016
    cur = conn.execute("""
        INSERT INTO cwl (sid, wid, cid, usrname)
        SELECT o.sid, o.wid, o.cid, o.usrname
        FROM old.cwl o
        WHERE NOT EXISTS (
            SELECT 1 FROM cwl c
            WHERE c.sid = o.sid AND c.wid = o.wid AND c.cid = o.cid
        )
    """)
    counts["cwl inserted"] = cur.rowcount
    print(f"  CWL inserted (2016-only): {cur.rowcount}")

    # 7. Insert sentiment rows only in 2016
    cur = conn.execute("""
        INSERT INTO sentiment (sid, cid, score, username)
        SELECT o.sid, o.cid, o.score, o.username
        FROM old.sentiment o
        WHERE NOT EXISTS (
            SELECT 1 FROM sentiment s
            WHERE s.sid = o.sid AND s.cid = o.cid
        )
    """)
    counts["sentiment inserted"] = cur.rowcount
    print(f"  Sentiment inserted (2016-only): {cur.rowcount}")

    # 8. Merge concept_log entries from 2016 that postdate raw's latest
    raw_latest = conn.execute(
        "SELECT max(date_update) FROM concept_log"
    ).fetchone()[0]
    print(f"  Raw concept_log latest: {raw_latest}")

    cur = conn.execute("""
        INSERT INTO concept_log
            (sid_new, sid_old, cid_new, cid_old,
             clemma_new, clemma_old, tag_new, tag_old,
             tags_new, tags_old, comment_new, comment_old,
             ntag_new, ntag_old, usrname_new, usrname_old,
             date_update)
        SELECT sid_new, sid_old, cid_new, cid_old,
               clemma_new, clemma_old, tag_new, tag_old,
               tags_new, tags_old, comment_new, comment_old,
               ntag_new, ntag_old, usrname_new, usrname_old,
               date_update
        FROM old.concept_log
        WHERE date_update > ?
    """, (raw_latest,))
    counts["concept_log merged"] = cur.rowcount
    print(f"  Concept_log entries merged: {cur.rowcount}")

    # Also merge word_log, cwl_log, sent_log entries newer than raw's latest
    for log_table, cols in [
        ("word_log", "sid_new, sid_old, wid_new, wid_old, word_new, word_old, "
                     "pos_new, pos_old, lemma_new, lemma_old, "
                     "cfrom_new, cfrom_old, cto_new, cto_old, "
                     "comment_new, comment_old, usrname_new, usrname_old, date_update"),
        ("cwl_log", "sid_new, sid_old, wid_new, wid_old, cid_new, cid_old, "
                    "usrname_new, usrname_old, date_update"),
        ("sent_log", "sid_new, sid_old, docID_new, docID_old, pid_new, pid_old, "
                     "sent_new, sent_old, comment_new, comment_old, "
                     "usrname_new, usrname_old, date_update"),
    ]:
        raw_max = conn.execute(
            f"SELECT max(date_update) FROM {log_table}"
        ).fetchone()[0]
        if raw_max:
            cur = conn.execute(f"""
                INSERT INTO {log_table} ({cols})
                SELECT {cols} FROM old.{log_table}
                WHERE date_update > ?
            """, (raw_max,))
        else:
            cur = conn.execute(f"""
                INSERT INTO {log_table} ({cols})
                SELECT {cols} FROM old.{log_table}
            """)
        counts[f"{log_table} merged"] = cur.rowcount
        print(f"  {log_table} entries merged: {cur.rowcount}")

    # Also merge sentiment_log and chunk_log/xwl_log if 2016 has them
    for log_table, cols in [
        ("sentiment_log", "sid_new, sid_old, cid_new, cid_old, "
                          "score_new, score_old, username_new, username_old, date_update"),
        ("xwl_log", "sid_new, sid_old, wid_new, wid_old, xid_new, xid_old, "
                    "username_new, username_old, date_update"),
    ]:
        try:
            raw_max = conn.execute(
                f"SELECT max(date_update) FROM {log_table}"
            ).fetchone()[0]
            if raw_max:
                cur = conn.execute(f"""
                    INSERT INTO {log_table} ({cols})
                    SELECT {cols} FROM old.{log_table}
                    WHERE date_update > ?
                """, (raw_max,))
            else:
                cur = conn.execute(f"""
                    INSERT INTO {log_table} ({cols})
                    SELECT {cols} FROM old.{log_table}
                """)
            counts[f"{log_table} merged"] = cur.rowcount
            print(f"  {log_table} entries merged: {cur.rowcount}")
        except sqlite3.OperationalError:
            pass

    conn.commit()

    # Verify final counts
    print("\nFinal row counts:")
    for t in ["sent", "word", "concept", "cwl", "sentiment"]:
        n = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"  {t:12s} {n}")

    tagged = conn.execute(
        "SELECT count(*) FROM concept WHERE tag IS NOT NULL AND tag != ''"
    ).fetchone()[0]
    total = conn.execute("SELECT count(*) FROM concept").fetchone()[0]
    print(f"\n  Tagged concepts: {tagged}/{total}")

    conn.execute("DETACH old")
    conn.close()
    print("\nDone. Backup at:", BACKUP)


if __name__ == "__main__":
    main()
