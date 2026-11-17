#!/usr/bin/env python3
"""Convert NTU-MC corpus databases to XML and back.

The XML format is defined by ``data/ntumc.dtd`` and described in
``docs/corpus-xml.md``.  One file holds any number of languages: each
``<Document>`` carries its own language, and an ``<Alignment>`` block at
the end holds the cross-lingual sentence, word and concept links that
the per-pair link databases store.

Usage::

    corpus_xml.py dump OUT.xml --db eng.db jpn.db [--link eng-jpn.db ...]
                  [--doc NAME ...] [--collection NAME ...]
    corpus_xml.py load IN.xml --outdir DIR [--renumber] [--user NAME]
    corpus_xml.py validate FILE.xml [--dtd data/ntumc.dtd]

``dump`` writes one XML file from one or more language databases plus
their link databases.  ``load`` creates (or appends to) ``LANG.db`` and
``FLANG-TLANG.db`` files in DIR from such a file.  Element ids follow
``LANG-dN``, ``LANG-sN``, ``LANG-sNwN``, ``LANG-sNcN`` and ``LANG-sNxN``;
``load`` keeps the numbers when the ids have that shape and the numbers
are free, and refuses otherwise unless ``--renumber`` assigns fresh ones.

The work is done by ``ntumc.corpus``: the databases are read into the
corpus model (``ntumc.corpus.db``), written as XML (``ntumc.corpus.xmlio``)
and loaded back through ``ntumc.corpus.dbwrite``.  ``python -m
ntumc.corpus`` offers the same commands for XML and JSON Lines alike.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ntumc.corpus import db, dbwrite, xmlio
from ntumc.corpus.dbwrite import LINK_SCHEMA, SCHEMA, WriteOptions
from ntumc.corpus.model import CorpusError
from ntumc.corpus.xmlio import DTD, clean

logger = logging.getLogger("corpus_xml")

LoadError = CorpusError
LoadOptions = WriteOptions

__all__ = [
    "DTD",
    "DumpOptions",
    "LoadError",
    "LoadOptions",
    "clean",
    "dump",
    "load",
    "main",
    "validate",
]


@dataclass
class DumpOptions:
    """What to write and how to label the ``<Corpus>`` element."""

    dbs: list[Path]
    links: list[Path] = field(default_factory=list)
    docs: set[str] | None = None
    collections: set[str] | None = None
    corpus_id: str = "ntumc"
    title: str | None = None
    license: str | None = None
    version: str | None = None


def dump(out: Path, opts: DumpOptions) -> dict[str, int]:
    """Write one XML file from language and link databases.

    Documents are streamed one at a time, so the whole corpus fits.  A copy
    of the DTD is put beside the output so that the DOCTYPE resolves.

    Args:
        out: Path of the XML file to write
        opts: Databases, filters and corpus-level labels

    Returns:
        Counts: documents per language and alignment elements

    Raises:
        ValueError: If no database is given
    """
    if not opts.dbs:
        raise ValueError("at least one language database is needed")
    select = db.Selection(opts.docs or set(), opts.collections or set())
    items = db.read_corpus(opts.dbs, opts.links, select)
    xml_opts = xmlio.XMLOptions(
        corpus_id=opts.corpus_id,
        title=opts.title,
        license=opts.license,
        version=opts.version,
        linguality="multilingual" if len(opts.dbs) > 1 else "monolingual",
    )
    return xmlio.write(items, out, xml_opts)


def load(
    xml_path: Path, outdir: Path, opts: WriteOptions | None = None
) -> dict[str, int]:
    """Load an XML file into the databases of a directory.

    Args:
        xml_path: The XML file
        outdir: Directory for ``LANG.db`` and ``FLANG-TLANG.db``
        opts: Id and default settings

    Returns:
        Counts of documents, sentences, words, concepts and links loaded

    Raises:
        CorpusError: On duplicate or dangling ids, or a missing genre
    """
    return dbwrite.write(xmlio.read(xml_path), outdir, opts)


def validate(xml_path: Path, dtd: Path = DTD) -> bool:
    """Validate a file against the DTD with xmllint.

    The file's DOCTYPE names ``ntumc.dtd``; a copy beside the file is used
    first, then the directory of ``dtd``, so the file need not have one.

    Args:
        xml_path: The XML file
        dtd: The DTD to validate against

    Returns:
        True if valid

    Raises:
        RuntimeError: If xmllint is not installed
    """
    if shutil.which("xmllint") is None:
        raise RuntimeError("xmllint is not installed (package libxml2-utils)")
    beside = xml_path.parent / dtd.name
    if beside.exists() and beside.read_bytes() != dtd.read_bytes():
        logger.warning("%s differs from %s and takes precedence", beside, dtd)
    res = subprocess.run(
        ["xmllint", "--noout", "--path", str(dtd.parent), "--valid", str(xml_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        lines = res.stderr.strip().splitlines()
        logger.error("%s", "\n".join(lines[:10]))
        if len(lines) > 10:
            logger.error("... %d more lines", len(lines) - 10)
    return res.returncode == 0


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Arguments without the program name (default: sys.argv[1:])

    Returns:
        Exit status
    """
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_dump = sub.add_parser("dump", help="write XML from corpus databases")
    p_dump.add_argument("out", type=Path, help="XML file to write")
    p_dump.add_argument(
        "--db",
        type=Path,
        nargs="+",
        required=True,
        help="language databases (eng.db ...)",
    )
    p_dump.add_argument(
        "--link",
        type=Path,
        nargs="*",
        default=[],
        help="link databases (eng-jpn.db ...)",
    )
    p_dump.add_argument("--doc", nargs="*", help="only these document names")
    p_dump.add_argument(
        "--collection", nargs="*", help="only these sub-corpora (story, kc ...)"
    )
    p_dump.add_argument(
        "--corpus-id", default="ntumc", help="Corpus corpusID attribute"
    )
    p_dump.add_argument(
        "--title", help="Corpus title (default: meta.title of the first database)"
    )
    p_dump.add_argument("--license", help="Corpus license (default: meta.license)")
    p_dump.add_argument("--version", help="Corpus version (default: meta.version)")

    p_load = sub.add_parser("load", help="load XML into corpus databases")
    p_load.add_argument("xml", type=Path, help="XML file to read")
    p_load.add_argument(
        "--outdir",
        type=Path,
        required=True,
        help="directory for LANG.db and FLANG-TLANG.db",
    )
    p_load.add_argument(
        "--renumber", action="store_true", help="always assign fresh docids and sids"
    )
    p_load.add_argument(
        "--skip-existing",
        action="store_true",
        help="pass over documents already in the database; alignments may still refer to them",
    )
    p_load.add_argument("--user", help="usrname for rows without last_changed_by")
    p_load.add_argument(
        "--schema", type=Path, default=SCHEMA, help="schema for new language databases"
    )
    p_load.add_argument(
        "--link-schema",
        type=Path,
        default=LINK_SCHEMA,
        help="schema for new link databases",
    )
    p_load.add_argument(
        "--no-validate", action="store_true", help="skip DTD validation before loading"
    )

    p_val = sub.add_parser("validate", help="validate XML against the DTD")
    p_val.add_argument("xml", type=Path, help="XML file to check")
    p_val.add_argument("--dtd", type=Path, default=DTD, help="DTD file")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if args.command == "dump":
        opts = DumpOptions(
            dbs=args.db,
            links=args.link,
            docs=set(args.doc) if args.doc else None,
            collections=set(args.collection) if args.collection else None,
            corpus_id=args.corpus_id,
            title=args.title,
            license=args.license,
            version=args.version,
        )
        counts = dump(args.out, opts)
        for key, n in sorted(counts.items()):
            print(f"{key}: {n}")
        return 0

    if args.command == "validate":
        ok = validate(args.xml, args.dtd)
        print(f"{args.xml}: {'valid' if ok else 'INVALID'}")
        return 0 if ok else 1

    if not args.no_validate and shutil.which("xmllint") and not validate(args.xml):
        logger.error("%s does not validate; fix it or pass --no-validate", args.xml)
        return 1
    opts = WriteOptions(
        args.renumber, args.skip_existing, args.user, args.schema, args.link_schema
    )
    try:
        counts = load(args.xml, args.outdir, opts)
    except CorpusError as exc:
        logger.error("%s", exc)
        return 1
    for key, n in sorted(counts.items()):
        print(f"{key}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
