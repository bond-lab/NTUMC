#!/usr/bin/env python3
"""Compare pristine Feb-2025 downloads against current build/ DBs.

For each language DB, report per-table row counts (pristine vs current),
and drill into sent/word/concept/cwl differences: rows deleted, added,
and (for concept) tag redistribution, so every change can be matched to
a documented branch fix.
"""

import sqlite3
import sys
from pathlib import Path

PRISTINE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/tmp/claude-1000/-home-bond-git-NTUMC/f6318767-d75a-4af6-9ca3-32719438f56d"
    "/scratchpad/pristine")
BUILD = Path("/home/bond/git/NTUMC/build")
LANGS = ["eng", "cmn", "jpn", "ind", "ita", "ces", "zsm", "yue"]


def tables(con: sqlite3.Connection) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def count(con: sqlite3.Connection, table: str) -> int:
    return con.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]


def key_diff(con: sqlite3.Connection, table: str, keys: str,
             where: str = "1=1") -> tuple[int, int]:
    """Rows only in pristine (p) and only in current (c), matched on keys."""
    only_p = con.execute(
        f"SELECT COUNT(*) FROM (SELECT {keys} FROM p.'{table}' WHERE {where} "
        f"EXCEPT SELECT {keys} FROM c.'{table}' WHERE {where})").fetchone()[0]
    only_c = con.execute(
        f"SELECT COUNT(*) FROM (SELECT {keys} FROM c.'{table}' WHERE {where} "
        f"EXCEPT SELECT {keys} FROM p.'{table}' WHERE {where})").fetchone()[0]
    return only_p, only_c


def tag_class(col: str = "tag") -> str:
    return (f"CASE WHEN {col} IS NULL OR {col}='' THEN 'empty' "
            f"WHEN {col} IN ('x','w','e') THEN {col} ELSE 'synset' END")


def main() -> None:
    for lang in LANGS:
        p_path = PRISTINE / f"{lang}.db"
        c_path = BUILD / f"{lang}.db"
        if not p_path.exists() or not c_path.exists():
            print(f"== {lang}: SKIP (missing file)")
            continue
        print(f"\n================ {lang} ================")
        con = sqlite3.connect(":memory:")
        con.execute(f"ATTACH '{p_path}' AS p")
        con.execute(f"ATTACH '{c_path}' AS c")
        pt = {r[0] for r in con.execute(
            "SELECT name FROM p.sqlite_master WHERE type='table'")}
        ct = {r[0] for r in con.execute(
            "SELECT name FROM c.sqlite_master WHERE type='table'")}
        if pt - ct:
            print(f"  tables only in pristine: {sorted(pt - ct)}")
        if ct - pt:
            print(f"  tables only in current:  {sorted(ct - pt)}")
        for t in sorted(pt & ct):
            np_ = con.execute(f"SELECT COUNT(*) FROM p.'{t}'").fetchone()[0]
            nc = con.execute(f"SELECT COUNT(*) FROM c.'{t}'").fetchone()[0]
            flag = "" if np_ == nc else "   <<<"
            print(f"  {t:<12} pristine={np_:>9}  current={nc:>9}{flag}")

        # Drill-downs on shared core tables.
        if "sent" in (pt & ct):
            op, oc = key_diff(con, "sent", "sid")
            if op or oc:
                print(f"  sent sids: only-pristine={op} only-current={oc}")
                for row in con.execute(
                        "SELECT sid, substr(sent,1,50) FROM p.sent "
                        "WHERE sid NOT IN (SELECT sid FROM c.sent) LIMIT 10"):
                    print(f"    lost sid {row[0]}: {row[1]!r}")
        if "word" in (pt & ct):
            op, oc = key_diff(con, "word", "sid, wid")
            if op or oc:
                print(f"  word keys: only-pristine={op} only-current={oc}")
        if "concept" in (pt & ct):
            op, oc = key_diff(con, "concept", "sid, cid")
            if op or oc:
                print(f"  concept keys: only-pristine={op} only-current={oc}")
            print("  concept tag classes (pristine -> current):")
            tc = tag_class()
            pdist = dict(con.execute(
                f"SELECT {tc}, COUNT(*) FROM p.concept GROUP BY 1"))
            cdist = dict(con.execute(
                f"SELECT {tc}, COUNT(*) FROM c.concept GROUP BY 1"))
            for k in sorted(set(pdist) | set(cdist)):
                a, b = pdist.get(k, 0), cdist.get(k, 0)
                flag = "" if a == b else "   <<<"
                print(f"    {k:<8} {a:>9} -> {b:>9}{flag}")
        if "cwl" in (pt & ct):
            op, oc = key_diff(con, "cwl", "sid, cid, wid")
            if op or oc:
                print(f"  cwl keys: only-pristine={op} only-current={oc}")
        con.close()


if __name__ == "__main__":
    main()
