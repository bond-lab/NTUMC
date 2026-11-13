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

To make a release from a base and its change records:

    python -m ntumc.wordnet apply BASE.xml CHANGES.jsonl NEW.xml [--version V]

``apply`` lists the changes that do not fit the base and, if there are
any, exits 1 without writing NEW.xml.

To get the change records that turn one version into another:

    python -m ntumc.wordnet diff OLD.xml NEW.xml CHANGES.jsonl \\
        --user U --source S --reason R [--base B]

``diff`` also applies the records to OLD and reports what still differs
from NEW (differences that have no change record); it exits 1 if the
records do not apply cleanly.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

from . import changes, jsonl, lmf, store
from . import diff as differ
from .model import Lexicon


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


def apply(base: Path, records: Path, out: Path, version: str | None = None) -> list[str]:
    """Apply change records to a base WN-LMF file and write the result.

    Args:
        base: the base release
        records: the change records (JSON Lines)
        out: the file to write; not written if there are conflicts
        version: the version of the new release (default: as the base)

    Returns:
        The conflicts, one line each
    """
    items, conflicts = changes.apply(lmf.read(base), changes.read(records))
    if conflicts:
        return conflicts
    if version:
        next(i for i in items if isinstance(i, Lexicon)).version = version
    lmf.write(out, items)
    return []


def diff(old: Path, new: Path, out: Path, **common: str) -> tuple[list[str], list[str]]:
    """Write the change records that turn ``old`` into ``new``.

    Args:
        old: the earlier WN-LMF file
        new: the later one
        out: where to write the records (JSON Lines)
        **common: ``user``, ``source``, ``reason`` and ``base`` for every record

    Returns:
        the conflicts, and one line per kind of difference left unexplained
    """
    lexicon = next(i for i in lmf.read(old) if isinstance(i, Lexicon)).id
    records = differ.diff(lmf.read(old), lmf.read(new), lexicon=str(lexicon), **common)
    counts = Counter(r.action for r in records)
    print(f"{changes.write(out, records)} records: "
          + ", ".join(f"{n} {a}" for a, n in sorted(counts.items())))
    conflicts, extra, missing = differ.residual(lmf.read(old), lmf.read(new), records)
    left = [f"{n} {kind} only in {side}"
            for side, facts in (("the result", extra), (new.name, missing))
            for kind, n in sorted(Counter(f[0] for f in facts.elements()).items())]
    return conflicts, left


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
    p = sub.add_parser("apply")
    p.add_argument("base", type=Path)
    p.add_argument("changes", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--version", help="version of the new release")
    p = sub.add_parser("diff")
    p.add_argument("old", type=Path)
    p.add_argument("new", type=Path)
    p.add_argument("out", type=Path)
    for name in ("user", "source", "reason"):
        p.add_argument(f"--{name}", required=True)
    p.add_argument("--base", help="the release the records are made against")
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
    elif a.cmd == "apply":
        conflicts = apply(a.base, a.changes, a.out, a.version)
        print("\n".join(conflicts) if conflicts else f"written: {a.out}")
        sys.exit(1 if conflicts else 0)
    elif a.cmd == "diff":
        common = {k: getattr(a, k) for k in ("user", "source", "reason", "base") if getattr(a, k)}
        conflicts, left = diff(a.old, a.new, a.out, **common)
        print("\n".join(conflicts + left) if conflicts or left else "nothing left unexplained")
        sys.exit(1 if conflicts else 0)
    else:
        diffs = check(a.db, a.keep) if a.cmd == "check" else check_lmf(a.xml, a.keep)
        print("\n".join(diffs) if diffs else "round trip: identical")
        sys.exit(1 if diffs else 0)


if __name__ == "__main__":
    main()
