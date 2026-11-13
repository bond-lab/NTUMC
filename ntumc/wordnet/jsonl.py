"""The wordnet model as a directory of JSON Lines files.

    schema.sql        the tables, indexes and triggers, to rebuild the database
    concepts.jsonl    one synset per line (kind "synset"), shared by all languages
    LANG.jsonl        per language: glosses (kind "gloss") then entries ("entry")
    other.jsonl       rows of unmodelled tables and orphans (kind "row")
    history.jsonl     the *_log tables (kind "row")

Each line is one object; keys are the model's fields, with None and
empty lists left out (an empty string is kept: it is not None).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import fields
from pathlib import Path
from typing import IO, Any

from .model import (
    Comment,
    Count,
    Entry,
    Form,
    Frame,
    Gloss,
    Item,
    Lexicon,
    Pronunciation,
    Relation,
    Requires,
    Row,
    Sense,
    SenseRelation,
    SenseXLink,
    Synset,
    Tag,
    Text,
    XLink,
)

KINDS: dict[str, type] = {"synset": Synset, "gloss": Gloss, "entry": Entry, "row": Row,
                          "lexicon": Lexicon, "frame": Frame}
NAMES = {cls: kind for kind, cls in KINDS.items()}
NESTED: dict[type, dict[str, type]] = {
    Lexicon: {"requires": Requires},
    Synset: {"relations": Relation, "xlinks": XLink, "comments": Comment,
             "definitions": Text, "ili_definition": Text, "examples": Text},
    Gloss: {"definitions": Text, "examples": Text},
    Entry: {"senses": Sense, "pronunciations": Pronunciation, "tags": Tag,
            "forms": Form, "frames": Frame},
    Form: {"pronunciations": Pronunciation, "tags": Tag},
    Sense: {"relations": SenseRelation, "xlinks": SenseXLink, "examples": Text,
            "counts": Count},
}
SEPARATOR = "\n-- ;;\n"


def to_dict(obj: Any) -> dict[str, Any]:
    """A model object as a JSON-ready dict, without None, empty lists or empty meta."""
    out: dict[str, Any] = {}
    for f in fields(obj):
        v = getattr(obj, f.name)
        if v is None or (isinstance(v, list | dict) and not v and f.name != "values"):
            continue
        out[f.name] = [to_dict(x) for x in v] if isinstance(v, list) else v
    return out


def from_dict(cls: type, d: dict[str, Any]) -> Any:
    """The inverse of ``to_dict``."""
    nested = NESTED.get(cls, {})
    return cls(**{k: [from_dict(nested[k], x) for x in v] if k in nested else v
                  for k, v in d.items()})


def dumps(item: Item) -> str:
    """One model object as a line of JSON, its ``kind`` first."""
    return json.dumps({"kind": NAMES[type(item)]} | to_dict(item), ensure_ascii=False)


def loads(line: str) -> Item:
    """The inverse of ``dumps``."""
    d = json.loads(line)
    return from_dict(KINDS[d.pop("kind")], d)


def _file_of(item: Item) -> str:
    if isinstance(item, Synset):
        return "concepts"
    if isinstance(item, Row):
        return "history" if item.table.endswith("_log") else "other"
    return str(item.lang)


def write_dir(outdir: Path, ddl: Iterable[tuple[str, str, str]], items: Iterable[Item]) -> dict[str, int]:
    """Write the schema and the model objects to ``outdir``.

    Returns:
        file stem -> number of lines written
    """
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "schema.sql").write_text(
        SEPARATOR.join(sql for _, _, sql in ddl) + "\n", encoding="utf-8")
    files: dict[str, IO[str]] = {}
    counts: dict[str, int] = {}
    try:
        for item in items:
            stem = _file_of(item)
            if stem not in files:
                files[stem] = (outdir / f"{stem}.jsonl").open("w", encoding="utf-8")
                counts[stem] = 0
            files[stem].write(dumps(item) + "\n")
            counts[stem] += 1
    finally:
        for f in files.values():
            f.close()
    return counts


def write_file(path: Path, items: Iterable[Item]) -> int:
    """Write model objects to one JSON Lines file; return the number of lines."""
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(dumps(item) + "\n")
            n += 1
    return n


def read_file(path: Path) -> Iterator[Item]:
    """Yield the model objects of one JSON Lines file."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            yield loads(line)


def read_schema(indir: Path) -> list[tuple[str, str, str]]:
    """(type, name, sql) from ``schema.sql``, as ``store.schema`` returns them."""
    out = []
    for sql in (indir / "schema.sql").read_text(encoding="utf-8").rstrip("\n").split(SEPARATOR):
        words = sql.split()
        kind = words[1].lower() if words[1].upper() != "UNIQUE" else words[2].lower()
        name = words[words.index(next(w for w in words if w.lower() == kind)) + 1]
        out.append((kind, name.strip('"').split("(")[0], sql))
    return out


def read_dir(indir: Path) -> Iterator[Item]:
    """Yield every model object in a directory written by ``write_dir``."""
    for path in sorted(indir.glob("*.jsonl")):
        yield from read_file(path)
