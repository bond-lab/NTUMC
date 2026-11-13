"""Dump the wordnet database to JSON Lines, load it back, and check the round trip.

    python -m ntumc.wordnet dump  build/wn-ntumc.db OUTDIR [--no-history]
    python -m ntumc.wordnet load  INDIR NEW.db
    python -m ntumc.wordnet check build/wn-ntumc.db [--keep DIR]

``check`` dumps the database, loads the dump into a new database and
compares the two: it exits 1 and lists the differences if any row or
any part of the schema did not survive.

The same for a WN-LMF file:

    python -m ntumc.wordnet lmf2jsonl WN.xml WN.jsonl
    python -m ntumc.wordnet jsonl2lmf WN.jsonl WN.xml
    python -m ntumc.wordnet check-lmf WN.xml [--keep DIR]

``check-lmf`` reads the XML, writes JSON Lines, reads that back, writes
XML and compares it with the original.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import jsonl, lmf, store


def dump(db: Path, outdir: Path, history: bool = True) -> dict[str, int]:
    """Write ``db`` to ``outdir`` as JSON Lines; return the line counts."""
    con = store.connect(db)
    ddl = store.schema(con)
    con.close()
    return jsonl.write_dir(outdir, ddl, store.read(db, history=history))


def load(indir: Path, db: Path) -> None:
    """Create ``db`` from a directory written by ``dump``."""
    store.write(db, jsonl.read_schema(indir), jsonl.read_dir(indir))


def check(db: Path, keep: Path | None = None) -> list[str]:
    """Round-trip ``db`` through JSON Lines; return the differences."""
    with tempfile.TemporaryDirectory() as tmp:
        work = keep or Path(tmp)
        counts = dump(db, work / "dump")
        for stem, n in sorted(counts.items()):
            print(f"  {stem}.jsonl\t{n}")
        new = work / "roundtrip.db"
        new.unlink(missing_ok=True)
        load(work / "dump", new)
        return store.compare(db, new)


def check_lmf(xml: Path, keep: Path | None = None) -> list[str]:
    """Round-trip a WN-LMF file through JSON Lines; return the differences."""
    with tempfile.TemporaryDirectory() as tmp:
        work = keep or Path(tmp)
        work.mkdir(parents=True, exist_ok=True)
        lines = work / (xml.stem + ".jsonl")
        print(f"  {lines.name}\t{jsonl.write_file(lines, lmf.read(xml))}")
        lmf.write(work / xml.name, jsonl.read_file(lines))
        return lmf.compare(xml, work / xml.name)


def main() -> None:
    """Command-line entry point."""
    ap = argparse.ArgumentParser(prog="python -m ntumc.wordnet", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump")
    p.add_argument("db", type=Path)
    p.add_argument("outdir", type=Path)
    p.add_argument("--no-history", action="store_true", help="leave out the *_log tables")
    p = sub.add_parser("load")
    p.add_argument("indir", type=Path)
    p.add_argument("db", type=Path)
    p = sub.add_parser("check")
    p.add_argument("db", type=Path)
    p.add_argument("--keep", type=Path, help="keep the dump and the new database here")
    p = sub.add_parser("lmf2jsonl")
    p.add_argument("xml", type=Path)
    p.add_argument("jsonl", type=Path)
    p = sub.add_parser("jsonl2lmf")
    p.add_argument("jsonl", type=Path)
    p.add_argument("xml", type=Path)
    p = sub.add_parser("check-lmf")
    p.add_argument("xml", type=Path)
    p.add_argument("--keep", type=Path, help="keep the JSON Lines and the new XML here")
    a = ap.parse_args()
    if a.cmd == "dump":
        for stem, n in sorted(dump(a.db, a.outdir, not a.no_history).items()):
            print(f"{stem}.jsonl\t{n}")
    elif a.cmd == "load":
        load(a.indir, a.db)
    elif a.cmd == "lmf2jsonl":
        print(f"{a.jsonl.name}\t{jsonl.write_file(a.jsonl, lmf.read(a.xml))}")
    elif a.cmd == "jsonl2lmf":
        lmf.write(a.xml, jsonl.read_file(a.jsonl))
    else:
        diffs = check(a.db, a.keep) if a.cmd == "check" else check_lmf(a.xml, a.keep)
        print("\n".join(diffs) if diffs else "round trip: identical")
        sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
