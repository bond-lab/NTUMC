"""JSON Lines serialisation of the corpus model.

Each line is one object with a ``kind`` of ``corpus``, ``document`` or
``alignment``; the other keys are the fields of the matching model
class, with None and empty lists left out.  A file is therefore read
and written one document at a time, and a document is a single
``json.loads``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import IO, Any

from .model import (
    Alignment,
    Chunk,
    Concept,
    ConceptLink,
    CorpusInfo,
    Document,
    Item,
    Sentence,
    SentLink,
    Word,
    WordLink,
)

KINDS: dict[str, type] = {
    "corpus": CorpusInfo,
    "document": Document,
    "alignment": Alignment,
}
# list-valued fields whose elements are model objects
NESTED: dict[type, dict[str, type]] = {
    Document: {"sentences": Sentence},
    Sentence: {"words": Word, "concepts": Concept, "chunks": Chunk},
    Alignment: {"sents": SentLink, "words": WordLink, "concepts": ConceptLink},
}
# fields dropped by the slim projection: annotation history and the
# per-concept candidate lists, which together double the size of a file
SLIM_DROP = {"user", "sentiment_user", "candidates", "comment", "stype_comment"}


def to_dict(obj: Any, slim: bool = False) -> dict[str, Any]:
    """Convert a model object to a JSON-ready dict.

    Args:
        obj: any model dataclass
        slim: leave out the fields in SLIM_DROP

    Returns:
        The dict, without None values or empty lists
    """
    out: dict[str, Any] = {}
    for f in fields(obj):
        if f.name == "_" or (slim and f.name in SLIM_DROP):
            continue
        value = getattr(obj, f.name)
        if value is None or value == []:
            continue
        if isinstance(value, list) and value and is_dataclass(value[0]):
            value = [to_dict(v, slim) for v in value]
        out[f.name] = value
    return out


def from_dict(cls: type, data: dict[str, Any]) -> Any:
    """Build a model object from a dict such as ``to_dict`` makes.

    Args:
        cls: the model class
        data: its fields; ``kind`` is ignored

    Returns:
        The object

    Raises:
        ValueError: on an unknown key
    """
    nested = NESTED.get(cls, {})
    names = {f.name for f in fields(cls)} - {"_"}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key == "kind":
            continue
        if key not in names:
            raise ValueError(f"{cls.__name__}: unknown field {key!r}")
        if key in nested:
            value = [from_dict(nested[key], v) for v in value]
        kwargs[key] = value
    return cls(**kwargs)


def _kind(obj: Item) -> str:
    for kind, cls in KINDS.items():
        if isinstance(obj, cls):
            return kind
    raise TypeError(f"not a corpus item: {type(obj).__name__}")


def dumps(obj: Item, slim: bool = False) -> str:
    """Serialise one item to a single JSON line (without the newline).

    Args:
        obj: a CorpusInfo, Document or Alignment
        slim: leave out the fields in SLIM_DROP

    Returns:
        The JSON text
    """
    record = {"kind": _kind(obj), **to_dict(obj, slim)}
    return json.dumps(record, ensure_ascii=False, separators=(",", ":"))


def loads(line: str) -> Item:
    """Parse one JSON line into a model object.

    Args:
        line: the JSON text

    Returns:
        A CorpusInfo, Document or Alignment

    Raises:
        ValueError: if the kind is missing or unknown, or a key is unknown
    """
    data = json.loads(line)
    kind = data.get("kind")
    if kind not in KINDS:
        raise ValueError(f"unknown record kind {kind!r}")
    return from_dict(KINDS[kind], data)


def write(items: Iterable[Item], out: Path | str | IO[str], slim: bool = False) -> int:
    """Write items as JSON Lines.

    Args:
        items: the stream to write
        out: a path or an open text file
        slim: leave out the fields in SLIM_DROP

    Returns:
        Number of lines written
    """
    if isinstance(out, (str, Path)):
        with open(out, "w", encoding="utf-8") as fh:
            return write(items, fh, slim)
    n = 0
    for item in items:
        out.write(dumps(item, slim))
        out.write("\n")
        n += 1
    return n


def read(src: Path | str | IO[str]) -> Iterator[Item]:
    """Yield the items of a JSON Lines file.

    Args:
        src: a path or an open text file

    Yields:
        One model object per non-blank line
    """
    if isinstance(src, (str, Path)):
        with open(src, encoding="utf-8") as fh:
            yield from read(fh)
        return
    for line in src:
        if line.strip():
            yield loads(line)
