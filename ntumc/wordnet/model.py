"""The NTU-MC wordnet as plain dataclasses.

One ``Synset`` per concept (shared by every language), one ``Gloss`` per
synset and language (definitions and examples), and one ``Entry`` per
word, holding its senses.  Everything else in the database (the
``*_log`` history, tables this model does not know, and rows whose
parent is missing) is carried as a ``Row`` so that nothing is lost.

Field names follow the database columns unless noted; ``usr`` is the
annotator who last changed the row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Value = str | int | float | None


@dataclass(slots=True)
class Relation:
    """A synset relation (table ``synlink``); ``target`` is ``synset2``."""

    link: Value = None
    target: Value = None
    src: Value = None
    usr: Value = None


@dataclass(slots=True)
class XLink:
    """A link from a synset to an outside resource (table ``xlink``)."""

    resource: Value = None
    xref: Value = None
    misc: Value = None
    confidence: Value = None
    usr: Value = None


@dataclass(slots=True)
class Comment:
    """An annotator's comment on a synset (table ``synset_comment``)."""

    comment: Value = None
    u: Value = None
    t: Value = None


@dataclass(slots=True)
class Synset:
    """A concept (table ``synset``); ``id`` is the ``synset`` column."""

    id: Value = None
    pos: Value = None
    name: Value = None
    src: Value = None
    usr: Value = None
    relations: list[Relation] = field(default_factory=list)
    xlinks: list[XLink] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)


@dataclass(slots=True)
class Text:
    """A definition or example (``synset_def``, ``synset_ex``); ``text`` is ``def``."""

    text: Value = None
    sid: Value = None
    usr: Value = None


@dataclass(slots=True)
class Gloss:
    """The definitions and examples of one synset in one language."""

    synset: Value = None
    lang: Value = None
    definitions: list[Text] = field(default_factory=list)
    examples: list[Text] = field(default_factory=list)


@dataclass(slots=True)
class SenseRelation:
    """A relation between two senses (table ``senslink``)."""

    link: Value = None
    synset2: Value = None
    wordid2: Value = None
    src: Value = None
    usr: Value = None


@dataclass(slots=True)
class SenseXLink:
    """A link from a sense to an outside resource (table ``xlinks``)."""

    lang: Value = None
    resource: Value = None
    xref: Value = None
    misc: Value = None
    confidence: Value = None
    usr: Value = None


@dataclass(slots=True)
class Sense:
    """A word in a synset (table ``sense``)."""

    synset: Value = None
    lang: Value = None
    rank: Value = None
    lexid: Value = None
    freq: Value = None
    src: Value = None
    confidence: Value = None
    usr: Value = None
    relations: list[SenseRelation] = field(default_factory=list)
    xlinks: list[SenseXLink] = field(default_factory=list)


@dataclass(slots=True)
class Entry:
    """A word (table ``word``) and its senses."""

    wordid: Value = None
    lang: Value = None
    lemma: Value = None
    pron: Value = None
    pos: Value = None
    usr: Value = None
    senses: list[Sense] = field(default_factory=list)


@dataclass(slots=True)
class Row:
    """A row kept as it is: history, an unmodelled table, or an orphan."""

    table: str = ""
    values: dict[str, Any] = field(default_factory=dict)


Item = Synset | Gloss | Entry | Row
