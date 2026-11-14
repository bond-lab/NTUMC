"""A lexicon without what a shared-concepts lexicon says, and with it again.

Concepts that several of our wordnets share before CILI has them live in
one shared lexicon (``omw-ntumc``): their English definition and their
relations.  A language wordnet is kept as a *minimal* lexicon (id
``cow-min``), which says only what is its own: its words, and for a
shared concept a synset carrying the concept's ``dc:identifier``.  The
*export* (id ``cow``) is built from the two, for users who want one file.

``minimal`` takes out of a lexicon exactly what ``export`` puts back, so

    export(minimal(lexicon)) == lexicon, plus what only the shared one has

A synset of the lexicon is the same concept as a synset of the shared
lexicon when they have the same ``dc:identifier`` or, failing that, the
same ILI.  The shared lexicon gives a synset

* its relations, where the lexicon also has the target, and
* its definitions, where the lexicon has none of its own for the synset.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from .model import Item, Lexicon, Relation, Requires, Synset, Text

IDENTIFIER = "dc:identifier"
SUFFIX = "-min"
LABEL = " (minimal)"

Supplied = dict[str, tuple[list[Text], list[Relation]]]


def _header(items: list[Item]) -> Lexicon:
    """The one lexicon header of ``items``."""
    headers = [i for i in items if isinstance(i, Lexicon)]
    if len(headers) != 1:
        raise ValueError(f"expected one lexicon, found {len(headers)}")
    return headers[0]


def supplied(items: Iterable[Item], shared: Iterable[Item]) -> Supplied:
    """What the shared lexicon says about the synsets of a lexicon.

    Args:
        items: the lexicon
        shared: the shared-concepts lexicon

    Returns:
        For each synset of the lexicon that carries a shared concept's
        identifier: the shared definitions, and the shared relations
        whose target the lexicon has, with the target as the lexicon's id

    Raises:
        ValueError: if two synsets of the lexicon have the same shared
            concept's identifier
    """
    concepts = [s for s in shared if isinstance(s, Synset)]
    wanted = {s.meta.get(IDENTIFIER) for s in concepts}
    by_identifier: dict[str, str] = {}
    by_ili: dict[str, str] = {}
    for s in items:
        if not isinstance(s, Synset):
            continue
        identifier = s.meta.get(IDENTIFIER)
        if identifier and identifier in wanted:
            if identifier in by_identifier:
                raise ValueError(f"{identifier} is on {by_identifier[identifier]} and {s.id}")
            by_identifier[identifier] = str(s.id)
        if s.ili and s.ili != "in":
            by_ili[s.ili] = str(s.id)
    same: dict[str, str] = {}  # shared synset id -> the lexicon's synset
    for s in concepts:
        here = by_identifier.get(s.meta.get(IDENTIFIER, "")) or by_ili.get(s.ili or "")
        if here:
            same[str(s.id)] = here
    out: Supplied = {}
    for s in concepts:
        here = by_identifier.get(s.meta.get(IDENTIFIER, ""))
        if here:
            out[here] = (
                [replace(d, meta=dict(d.meta)) for d in s.definitions],
                [Relation(link=r.link, target=same[str(r.target)])
                 for r in s.relations if r.target in same])
    return out


def _texts(definitions: list[Text]) -> set[tuple[str | None, str]]:
    return {(d.lang, str(d.text)) for d in definitions}


def minimal(items: Iterable[Item], shared: Iterable[Item]) -> tuple[list[Item], dict[str, int]]:
    """Take out of a lexicon what the shared lexicon says; name it ``ID-min``.

    The lexicon's objects are changed in place.  A definition stays if
    the synset has any definition the shared lexicon does not have:
    ``export`` only fills in a synset that has none.

    Args:
        items: the lexicon, with everything in it
        shared: the shared-concepts lexicon

    Returns:
        The minimal lexicon, and how many ``definitions`` and
        ``relations`` were taken out of how many ``concepts``
    """
    items, shared = list(items), list(shared)
    counts = {"concepts": 0, "definitions": 0, "relations": 0}
    theirs = supplied(items, shared)
    for s in items:
        if not isinstance(s, Synset) or s.id not in theirs:
            continue
        definitions, relations = theirs[str(s.id)]
        counts["concepts"] += 1
        if s.definitions and _texts(s.definitions) <= _texts(definitions):
            counts["definitions"] += len(s.definitions)
            s.definitions = []
        known = {(r.link, r.target) for r in relations}
        kept = [r for r in s.relations if (r.link, r.target) not in known]
        counts["relations"] += len(s.relations) - len(kept)
        s.relations = kept
    header, source = _header(items), _header(shared)
    header.id = f"{header.id}{SUFFIX}"
    header.label = f"{header.label}{LABEL}"
    header.requires.append(Requires(ref=source.id, version=source.version))
    return items, counts


def export(items: Iterable[Item], shared: Iterable[Item]) -> tuple[list[Item], dict[str, int]]:
    """Put what the shared lexicon says into a minimal lexicon; name it ``ID``.

    The lexicon's objects are changed in place.

    Args:
        items: the minimal lexicon
        shared: the shared-concepts lexicon

    Returns:
        The export, and how many ``definitions`` and ``relations`` were
        put into how many ``concepts``

    Raises:
        ValueError: if the lexicon is not a minimal one
    """
    items, shared = list(items), list(shared)
    header, source = _header(items), _header(shared)
    if not str(header.id).endswith(SUFFIX):
        raise ValueError(f"{header.id} is not a minimal lexicon")
    counts = {"concepts": 0, "definitions": 0, "relations": 0}
    theirs = supplied(items, shared)
    for s in items:
        if not isinstance(s, Synset) or s.id not in theirs:
            continue
        definitions, relations = theirs[str(s.id)]
        counts["concepts"] += 1
        if not s.definitions:
            s.definitions = definitions
            counts["definitions"] += len(definitions)
        have = {(r.link, r.target) for r in s.relations}
        new = [r for r in relations if (r.link, r.target) not in have]
        s.relations += new
        counts["relations"] += len(new)
    header.id = str(header.id).removesuffix(SUFFIX)
    header.label = str(header.label).removesuffix(LABEL)
    header.requires = [r for r in header.requires if r.ref != source.id]
    return items, counts
