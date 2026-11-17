"""Command line: convert between databases, XML and JSON Lines, and validate.

The format of a file is taken from its suffix: ``.xml`` or ``.jsonl``.

Usage::

    python -m ntumc.corpus dump OUT.{jsonl,xml} --db eng.db jpn.db [--link eng-jpn.db]
                                 [--doc NAME ...] [--collection NAME ...] [--slim]
    python -m ntumc.corpus convert IN.{jsonl,xml} OUT.{jsonl,xml} [--slim]
    python -m ntumc.corpus load IN.{jsonl,xml} --outdir DIR [--renumber] [--skip-existing]
                                 [--user NAME]
    python -m ntumc.corpus validate FILE.{jsonl,xml}
    python -m ntumc.corpus validate --db eng.db jpn.db [--link eng-jpn.db]

``validate`` runs the semantic checks of ``ntumc.corpus.validate``; the
DTD check of an XML file is ``scripts/corpus_xml.py validate``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from . import db, dbwrite, jsonl, xmlio
from .model import CorpusError, Item
from .validate import validate

logger = logging.getLogger("ntumc.corpus")


def read_file(path: Path) -> Iterable[Item]:
    """Read a JSON Lines or XML file, by suffix.

    Args:
        path: the file

    Returns:
        Its items

    Raises:
        ValueError: on another suffix
    """
    if path.suffix == ".xml":
        return xmlio.read(path)
    if path.suffix == ".jsonl":
        return jsonl.read(path)
    raise ValueError(f"{path}: expected a .jsonl or .xml file")


def write_file(items: Iterable[Item], path: Path, slim: bool = False) -> int:
    """Write items to a JSON Lines or XML file, by suffix.

    Args:
        items: the stream to write
        path: the file
        slim: JSON Lines only: leave out history and candidates

    Returns:
        Number of records (JSON Lines) or elements (XML) written

    Raises:
        ValueError: on another suffix
    """
    if path.suffix == ".xml":
        return sum(xmlio.write(items, path).values())
    if path.suffix == ".jsonl":
        return jsonl.write(items, path, slim=slim)
    raise ValueError(f"{path}: expected a .jsonl or .xml file")


def _items(args: argparse.Namespace) -> Iterable[Item]:
    if getattr(args, "db", None):
        select = db.Selection(set(args.doc or []), set(args.collection or []))
        return db.read_corpus(args.db, args.link or [], select)
    return read_file(args.file)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def source(p: argparse.ArgumentParser, file: bool) -> None:
        if file:
            p.add_argument("file", nargs="?", type=Path, help="JSON Lines or XML file")
        p.add_argument("--db", nargs="+", type=Path, help="corpus databases")
        p.add_argument("--link", nargs="*", type=Path, help="link databases")
        p.add_argument("--doc", nargs="+", help="only these documents")
        p.add_argument("--collection", nargs="+", help="only these collections")

    d = sub.add_parser("dump", help="write a JSON Lines or XML file from databases")
    d.add_argument("out", type=Path)
    source(d, file=False)
    d.add_argument(
        "--slim", action="store_true", help="leave out history and candidates"
    )

    c = sub.add_parser("convert", help="JSON Lines to XML or back")
    c.add_argument("file", type=Path)
    c.add_argument("out", type=Path)
    c.add_argument(
        "--slim", action="store_true", help="leave out history and candidates"
    )

    ld = sub.add_parser("load", help="load a JSON Lines or XML file into databases")
    ld.add_argument("file", type=Path)
    ld.add_argument(
        "--outdir", type=Path, required=True, help="directory for the databases"
    )
    ld.add_argument(
        "--renumber", action="store_true", help="assign fresh docids and sids"
    )
    ld.add_argument(
        "--skip-existing", action="store_true", help="pass over documents already there"
    )
    ld.add_argument("--user", help="user for rows that have none")

    v = sub.add_parser("validate", help="check a file or databases")
    source(v, file=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: command line (default sys.argv[1:])

    Returns:
        Exit status: 1 on a load error or when validate found errors
    """
    parser = _parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        if args.command == "dump":
            if not args.db:
                parser.error("dump needs --db")
            n = write_file(_items(args), args.out, slim=args.slim)
            logger.info("%s: %d records", args.out, n)
            return 0
        if args.command == "convert":
            n = write_file(read_file(args.file), args.out, slim=args.slim)
            logger.info("%s: %d records", args.out, n)
            return 0
        if args.command == "load":
            opts = dbwrite.WriteOptions(args.renumber, args.skip_existing, args.user)
            counts = dbwrite.write(read_file(args.file), args.outdir, opts)
            for key, n in sorted(counts.items()):
                print(f"{key}: {n}")
            return 0
        if not args.db and not args.file:
            parser.error("validate needs a file or --db")
        counts: Counter[str] = Counter()
        for problem in validate(_items(args)):
            counts[problem.level] += 1
            print(problem)
        print(f"{counts['error']} errors, {counts['warning']} warnings")
        return 1 if counts["error"] else 0
    except (CorpusError, ValueError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
