"""Read and write WN-LMF XML through the wordnet model.

``read`` yields a ``Lexicon`` and then its ``Entry``, ``Synset`` and
``Frame`` objects in file order; ``write`` is its inverse.  ``compare``
checks that two files hold the same elements, attributes and text
(ignoring layout, attribute order and comments), so that

    read -> write -> compare

proves nothing in a release file is lost.  Reading fails on an element
or attribute the model has no place for.  ``LexiconExtension`` is not
handled yet.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from typing import IO, Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from .model import (
    Count,
    Entry,
    Form,
    Frame,
    Item,
    Lexicon,
    Pronunciation,
    Relation,
    Requires,
    Sense,
    SenseRelation,
    Synset,
    Tag,
    Text,
)

DTD = "https://globalwordnet.github.io/schemas/WN-LMF-1.4.dtd"
META = {"status", "note", "confidenceScore"}  # metadata attributes without a prefix
ATTR_ESCAPES = {"\n": "&#10;", "\r": "&#13;", "\t": "&#9;"}


@dataclass(frozen=True)
class Spec:
    """How one model class is written as an XML element.

    Attributes:
        cls: the model class
        attrs: XML attribute -> field
        children: (XML element, field) in the order the DTD wants them
        text: the field holding the element's text, if it has text
        meta: whether metadata attributes are allowed
    """

    cls: type
    attrs: dict[str, str] = field(default_factory=dict)
    children: tuple[tuple[str, str], ...] = ()
    text: str | None = None
    meta: bool = True


SPECS: dict[str, Spec] = {
    "Requires": Spec(Requires, {"ref": "ref", "id": "id", "version": "version", "url": "url"}),
    "Pronunciation": Spec(Pronunciation, {"variety": "variety", "notation": "notation",
                                          "phonemic": "phonemic", "audio": "audio"},
                          text="text", meta=False),
    "Tag": Spec(Tag, {"category": "category"}, text="text", meta=False),
    "Form": Spec(Form, {"id": "id", "writtenForm": "form", "script": "script"},
                 (("Pronunciation", "pronunciations"), ("Tag", "tags")), meta=False),
    "Count": Spec(Count, text="text"),
    "Example": Spec(Text, {"language": "lang"}, text="text"),
    "Definition": Spec(Text, {"language": "lang", "sourceSense": "source_sense"}, text="text"),
    "ILIDefinition": Spec(Text, text="text"),
    "SenseRelation": Spec(SenseRelation, {"relType": "link", "target": "target"}),
    "SynsetRelation": Spec(Relation, {"relType": "link", "target": "target"}),
    "SyntacticBehaviour": Spec(Frame, {"id": "id", "subcategorizationFrame": "frame",
                                       "senses": "senses"}, meta=False),
    "Sense": Spec(Sense, {"id": "id", "synset": "synset", "lexicalized": "lexicalized",
                          "adjposition": "adjposition", "subcat": "subcat", "n": "n"},
                  (("SenseRelation", "relations"), ("Example", "examples"), ("Count", "counts"))),
    "Synset": Spec(Synset, {"id": "id", "ili": "ili", "partOfSpeech": "pos",
                            "lexicalized": "lexicalized", "members": "members",
                            "lexfile": "lexfile"},
                   (("Definition", "definitions"), ("ILIDefinition", "ili_definition"),
                    ("SynsetRelation", "relations"), ("Example", "examples"))),
    # the Lemma element is folded into the entry: see _entry and _write_entry
    "LexicalEntry": Spec(Entry, {"id": "id", "index": "index"},
                         (("Form", "forms"), ("Sense", "senses"),
                          ("SyntacticBehaviour", "frames"))),
    "Lexicon": Spec(Lexicon, {k: k for k in ("id", "label", "language", "email", "license",
                                             "version", "url", "citation", "logo")},
                    (("Requires", "requires"),)),
}
LEMMA = Spec(Entry, {"writtenForm": "lemma", "script": "script", "partOfSpeech": "pos"},
             (("Pronunciation", "pronunciations"), ("Tag", "tags")), meta=False)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fill(obj: Any, elem: ET.Element, spec: Spec, prefixes: dict[str, str]) -> None:
    """Copy an element's attributes, text and children into ``obj``."""
    name = _local(elem.tag)
    for key, value in elem.attrib.items():
        if key in spec.attrs:
            setattr(obj, spec.attrs[key], value)
        elif spec.meta and key in META:
            obj.meta[key] = value
        elif spec.meta and key.startswith("{") and key[1:].split("}")[0] in prefixes:
            uri, local = key[1:].split("}")
            obj.meta[f"{prefixes[uri]}:{local}"] = value
        else:
            raise ValueError(f"{name}: no model field for attribute {key}")
    if spec.text:
        setattr(obj, spec.text, elem.text or "")
    fields_of = dict(spec.children)
    for child in elem:
        tag = _local(child.tag)
        if tag == "Lemma" and spec.cls is Entry:
            _fill(obj, child, LEMMA, prefixes)
        elif tag in fields_of:
            sub = SPECS[tag]
            new = sub.cls()
            _fill(new, child, sub, prefixes)
            getattr(obj, fields_of[tag]).append(new)
        else:
            raise ValueError(f"{name}: no model field for element {tag}")


def _doctype(path: Path) -> str | None:
    """The DOCTYPE system identifier, read from the head of the file."""
    with path.open(encoding="utf-8") as f:
        m = re.search(r'<!DOCTYPE\s+LexicalResource\s+SYSTEM\s+"([^"]*)"', f.read(2000))
    return m.group(1) if m else None


def read(path: Path) -> Iterator[Item]:
    """Yield the lexicons of a WN-LMF file and their contents, in file order.

    Args:
        path: a WN-LMF XML file

    Yields:
        each ``Lexicon``, followed by its ``Entry``, ``Synset`` and
        ``Frame`` objects

    Raises:
        ValueError: for an element or attribute the model cannot hold
    """
    dtd = _doctype(path)
    prefixes: dict[str, str] = {}  # namespace URI -> prefix
    lexicon: Lexicon | None = None
    waiting = False  # the lexicon has not been yielded yet
    depth = 0
    for event, node in ET.iterparse(path, events=("start-ns", "start", "end")):
        if event == "start-ns":
            prefixes[node[1]] = node[0]
            continue
        tag = _local(node.tag)
        if event == "start":
            depth += 1
            if depth == 2:
                if tag != "Lexicon":
                    raise ValueError(f"{tag} is not handled yet")
                lexicon = Lexicon(dtd=dtd, namespaces={p: u for u, p in prefixes.items()})
                _fill(lexicon, ET.Element(node.tag, node.attrib), SPECS["Lexicon"], prefixes)
                waiting = True
            continue
        depth -= 1
        if depth == 2 and lexicon is not None:
            if tag == "Requires":
                req = Requires()
                _fill(req, node, SPECS[tag], prefixes)
                lexicon.requires.append(req)
                continue
            if waiting:
                yield lexicon
                waiting = False
            if tag not in ("LexicalEntry", "Synset", "SyntacticBehaviour"):
                raise ValueError(f"Lexicon: no model field for element {tag}")
            spec = SPECS[tag]
            obj = spec.cls()
            _fill(obj, node, spec, prefixes)
            yield obj
            node.clear()
        elif depth == 1:
            if waiting and lexicon is not None:
                yield lexicon
                waiting = False
            node.clear()


def _attrs(obj: Any, spec: Spec) -> str:
    """The attributes of an element, as XML text."""
    pairs = [(xml, getattr(obj, name)) for xml, name in spec.attrs.items()]
    if spec.meta:
        pairs += list(obj.meta.items())
    return "".join(f" {k}={quoteattr(v, ATTR_ESCAPES)}" for k, v in pairs if v is not None)


def _write(out: IO[str], tag: str, obj: Any, depth: int) -> None:
    """Write one model object, and everything under it, as an element."""
    spec = SPECS[tag]
    pad = "  " * depth
    out.write(f"{pad}<{tag}{_attrs(obj, spec)}")
    if spec.text:
        out.write(f">{escape(getattr(obj, spec.text) or '')}</{tag}>\n")
        return
    kids = [(t, child) for t, name in spec.children for child in getattr(obj, name)]
    if not kids and spec.cls is not Entry:
        out.write(" />\n")
        return
    out.write(">\n")
    if spec.cls is Entry:
        _write_lemma(out, obj, depth + 1)
    for t, child in kids:
        _write(out, t, child, depth + 1)
    out.write(f"{pad}</{tag}>\n")


def _write_lemma(out: IO[str], entry: Entry, depth: int) -> None:
    pad = "  " * depth
    out.write(f"{pad}<Lemma{_attrs(entry, LEMMA)}")
    kids = [("Pronunciation", p) for p in entry.pronunciations] + [("Tag", t) for t in entry.tags]
    if not kids:
        out.write(" />\n")
        return
    out.write(">\n")
    for t, child in kids:
        _write(out, t, child, depth + 1)
    out.write(f"{pad}</Lemma>\n")


TAGS = {Entry: "LexicalEntry", Synset: "Synset", Frame: "SyntacticBehaviour"}


def write(path: Path, items: Iterable[Item]) -> None:
    """Write model objects as a WN-LMF file.

    Args:
        path: the file to write
        items: each ``Lexicon`` followed by its entries, synsets and frames

    Raises:
        ValueError: if an item comes before any lexicon, or cannot be
            written as WN-LMF (a ``Gloss`` or ``Row``)
    """
    with path.open("w", encoding="utf-8") as out:
        inside = False
        for item in items:
            if isinstance(item, Lexicon):
                if inside:
                    out.write("  </Lexicon>\n")
                else:
                    ns = "".join(f" xmlns:{p}={quoteattr(u)}" for p, u in item.namespaces.items())
                    out.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                              f'<!DOCTYPE LexicalResource SYSTEM "{item.dtd or DTD}">\n'
                              f"<LexicalResource{ns}>\n")
                inside = True
                out.write(f"  <Lexicon{_attrs(item, SPECS['Lexicon'])}>\n")
                for req in item.requires:
                    _write(out, "Requires", req, 2)
            elif type(item) not in TAGS:
                raise ValueError(f"{type(item).__name__} cannot be written as WN-LMF")
            elif not inside:
                raise ValueError("the first item must be a Lexicon")
            else:
                _write(out, TAGS[type(item)], item, 2)
        if inside:
            out.write("  </Lexicon>\n</LexicalResource>\n")


def _events(path: Path) -> Iterator[tuple]:
    """Each element of a file, as it ends: tag, attributes, text, child count."""
    for _, node in ET.iterparse(path, events=("end",)):
        leaf = len(node) == 0
        yield (node.tag, tuple(sorted(node.attrib.items())),
               (node.text or "") if leaf else "", len(node))
        node.clear()


def compare(a: Path, b: Path, limit: int = 20) -> list[str]:
    """Differences between two XML files, ignoring layout and attribute order.

    Args:
        a: one file
        b: the other
        limit: stop after this many differences

    Returns:
        One line per difference; empty when the files are equivalent
    """
    out = []
    if _doctype(a) != _doctype(b):
        out.append(f"DOCTYPE: {_doctype(a)} != {_doctype(b)}")
    for n, (x, y) in enumerate(zip_longest(_events(a), _events(b)), start=1):
        if x != y:
            out.append(f"element {n}: {x} != {y}")
            if len(out) >= limit:
                break
    return out
