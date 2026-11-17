"""JSON Schema for the JSON Lines format, generated from the model.

The schema (draft 2020-12) describes one record, that is one line of a
file: a ``corpus``, ``document`` or ``alignment`` object as ``jsonl``
writes it.  It is built from the dataclasses in ``model`` so that it
cannot drift from them, and a copy is kept at ``data/ntumc.schema.json``
beside the DTD for people who read the files with other tools.

``check`` validates a parsed record and ``check_file`` a whole file,
line by line, so that a corpus of any size can be checked.  Records are
checked with ``fastjsonschema`` (compiled, about ten times faster than
``jsonschema`` on a corpus dump); a record that fails is then run
through ``jsonschema`` for the full list of what is wrong.
"""

from __future__ import annotations

import json
import types
import typing
from collections.abc import Callable, Iterator
from dataclasses import MISSING, dataclass, field, fields
from pathlib import Path
from typing import Any

import fastjsonschema
import jsonschema

from . import model
from .jsonl import KINDS, NESTED
from .validate import Problem

SCHEMA_ID = "https://github.com/bond-lab/NTUMC/blob/main/data/ntumc.schema.json"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "ntumc.schema.json"
MAX_ERRORS_PER_RECORD = 20

_TYPES = {int: "integer", str: "string", float: "number", bool: "boolean"}

# one line per field, for readers of the schema; the model docstring has
# the renamings from the database columns
FIELD_DOCS = {
    "docid": "document id, unique within the language",
    "doc": "short machine name of the document, e.g. catb",
    "language": "ISO 639-3 code: eng, jpn, cmn, ind, ...",
    "title": "title (of the corpus, document or collection)",
    "subtitle": "subtitle of the document",
    "url": "where the text came from",
    "collection": "short name of the sub-corpus, e.g. story, kc, essay",
    "collection_title": "title of the sub-corpus",
    "genre": "genre of the sub-corpus",
    "sentences": "the sentences, in order",
    "sid": "sentence id, unique within the language",
    "text": "the sentence text",
    "pid": "paragraph id",
    "stype": "structural type: p (paragraph start), h0-h7 (heading), item, ...",
    "stype_comment": "comment on the structural type",
    "comment": "annotator's comment",
    "user": "who last changed this",
    "words": "the words of the sentence, or the word links of an alignment",
    "concepts": "the concepts of the sentence, or the concept links",
    "chunks": "the chunks of the sentence",
    "wid": "word id within the sentence, from 0",
    "word": "surface form",
    "lemma": "lemma",
    "pos": "part of speech in the language's own tagset",
    "cfrom": "offset of the first character in the text",
    "cto": "offset after the last character (text[cfrom:cto] == word)",
    "cid": "concept id within the sentence, from 0",
    "clemma": "the lemma as tagged, may be a multiword expression",
    "tag": "synset id such as 02084071-n, or e, w, x; absent if untagged",
    "wids": "the words covered",
    "ne": "named-entity type: per, org, loc, dat, num, oth, nam",
    "candidates": "the senses the annotator chose from",
    "sentiment": "sentiment score, -100 to 100",
    "sentiment_user": "who gave the sentiment score",
    "xid": "chunk id within the sentence",
    "score": "sentiment score of the chunk",
    "flang": "language of the from side",
    "tlang": "language of the to side",
    "fdoc": "docid of the from-side document the links belong to",
    "sents": "the sentence links",
    "fsid": "from sentence",
    "tsid": "to sentence",
    "fwid": "from word",
    "twid": "to word",
    "fcid": "from concept",
    "tcid": "to concept",
    "ltype": "link type; for concept links the wordnet relation =, <, >, ~, !",
    "conf": "confidence, 0.0 to 1.0",
    "license": "license of the corpus",
    "version": "version of the corpus",
}
ENUMS = {"genre": model.GENRES}


def _field_schema(cls: type, name: str, hint: Any) -> dict[str, Any]:
    """Schema of one field from its type hint."""
    optional = False
    args = typing.get_args(hint)
    if isinstance(hint, types.UnionType) or typing.get_origin(hint) is typing.Union:
        optional = type(None) in args
        args = tuple(a for a in args if a is not type(None))
        if len(args) != 1:
            raise TypeError(f"{cls.__name__}.{name}: unsupported union {hint}")
        hint = args[0]
    out: dict[str, Any]
    if typing.get_origin(hint) is list:
        (item,) = typing.get_args(hint)
        nested = NESTED.get(cls, {}).get(name)
        out = {"type": "array"}
        out["items"] = (
            {"$ref": f"#/$defs/{nested.__name__}"} if nested else {"type": _TYPES[item]}
        )
    elif hint in _TYPES:
        out = {"type": [_TYPES[hint], "null"] if optional else _TYPES[hint]}
    else:
        raise TypeError(f"{cls.__name__}.{name}: unsupported type {hint}")
    if name in ENUMS:
        out["enum"] = list(ENUMS[name]) + ([None] if optional else [])
    if name in FIELD_DOCS:
        out["description"] = FIELD_DOCS[name]
    return out


def _class_schema(cls: type) -> dict[str, Any]:
    """Schema of one model class (without the ``kind`` key)."""
    hints = typing.get_type_hints(cls)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in fields(cls):
        if f.name == "_":
            continue
        properties[f.name] = _field_schema(cls, f.name, hints[f.name])
        if f.default is MISSING and f.default_factory is MISSING:
            required.append(f.name)
    out: dict[str, Any] = {
        "type": "object",
        "description": (cls.__doc__ or "").strip().split("\n")[0],
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        out["required"] = required
    return out


def build() -> dict[str, Any]:
    """Build the schema of one JSON Lines record from the model classes.

    Returns:
        The schema as a dict ready for ``json.dump``
    """
    defs: dict[str, Any] = {}
    for cls in KINDS.values():
        defs[cls.__name__] = _class_schema(cls)
    for nested in NESTED.values():
        for cls in nested.values():
            defs[cls.__name__] = _class_schema(cls)
    variants = []
    for kind, cls in KINDS.items():
        record = _class_schema(cls)
        record["properties"] = {
            "kind": {"const": kind, "description": "record type"},
            **record["properties"],
        }
        record["required"] = ["kind"] + record.get("required", [])
        variants.append(record)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "NTU-MC corpus record",
        "description": (
            "One line of a JSON Lines corpus file: the corpus metadata, "
            "a document in one language, or the alignments from one "
            "document to another language. Generated from ntumc.corpus.model "
            "by `python -m ntumc.corpus schema`."
        ),
        "oneOf": variants,
        "$defs": defs,
    }


def dumps() -> str:
    """Return the schema as formatted JSON text, as kept in the repository."""
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


UNKNOWN_KIND = "record is not a corpus, document or alignment"


@dataclass
class Checker:
    """Compiled validators for one schema, one per record kind.

    ``fast`` holds the fastjsonschema functions, which raise on the
    first error; ``slow`` is the jsonschema validator of the same kind,
    used to list every error of a failing record.
    """

    schema: dict[str, Any]
    fast: dict[str, Callable[[Any], Any]] = field(default_factory=dict)
    slow: dict[str, jsonschema.Draft202012Validator] = field(default_factory=dict)

    @classmethod
    def build(cls) -> Checker:
        """Compile the schema of the current model.

        Returns:
            The checker
        """
        schema = build()
        jsonschema.Draft202012Validator.check_schema(schema)
        checker = cls(schema)
        for variant in schema["oneOf"]:
            kind = variant["properties"]["kind"]["const"]
            one = {**variant, "$defs": schema["$defs"]}
            checker.fast[kind] = fastjsonschema.compile(one)
            checker.slow[kind] = jsonschema.Draft202012Validator(one)
        return checker

    def errors(self, record: Any) -> list[str]:
        """Validate one parsed record.

        Args:
            record: a parsed JSON line

        Returns:
            Error messages with the path into the record, empty if it is
            valid; at most MAX_ERRORS_PER_RECORD of them
        """
        kind = record.get("kind") if isinstance(record, dict) else None
        if kind not in self.fast:
            return [UNKNOWN_KIND]
        try:
            self.fast[kind](record)
        except fastjsonschema.JsonSchemaValueException:
            pass
        else:
            return []
        found = sorted(
            self.slow[kind].iter_errors(record), key=lambda e: list(e.absolute_path)
        )
        return [f"{e.json_path}: {e.message}" for e in found[:MAX_ERRORS_PER_RECORD]]


def validator() -> Checker:
    """Compile the schema of the current model.

    Returns:
        A ``Checker``
    """
    return Checker.build()


def check(record: Any, checker: Checker | None = None) -> list[str]:
    """Validate one parsed record against the schema.

    Args:
        record: a parsed JSON line
        checker: from ``validator()``, made if not given

    Returns:
        Error messages, empty if the record is valid
    """
    return (checker or validator()).errors(record)


def check_file(path: Path | str) -> Iterator[Problem]:
    """Validate every line of a JSON Lines file against the schema.

    Args:
        path: the file

    Yields:
        One ``Problem`` (level error, code ``json`` or ``schema``) per
        unparsable line or schema error
    """
    checker = validator()
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            where = f"line {n}"
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                yield Problem("error", "json", where, str(exc))
                continue
            for message in check(record, checker):
                yield Problem("error", "schema", where, message)
