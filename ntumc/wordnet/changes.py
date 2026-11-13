"""Change records, and applying them to a lexicon.

The master copy of a wordnet is a base release (WN-LMF) plus an ordered
list of changes, one JSON object per line.  ``apply`` makes the changes
to the model objects of the base; what comes out is the next release.

A change that does not fit the base (its sense is not there, its
``old`` value is not the current one, the sense it adds exists) is a
conflict.  Conflicts are returned, not skipped silently: a release
should not be written until a person has settled them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .model import (
    Entry,
    Form,
    Frame,
    Item,
    Lexicon,
    Relation,
    Sense,
    SenseRelation,
    Synset,
    Text,
)

# action -> the fields it needs, besides those every change needs
ACTIONS: dict[str, tuple[str, ...]] = {
    "add_sense": ("synset", "lemma"),
    "remove_sense": ("synset", "lemma"),
    "keep_sense": ("synset", "lemma"),
    "set_confidence": ("synset", "lemma", "new"),
    "rename_lemma": ("synset", "lemma", "new"),
    "add_form": ("lemma", "pos", "new"),
    "remove_form": ("lemma", "pos", "old"),
    "set_definition": ("synset", "new"),
    "add_example": ("synset", "new"),
    "add_relation": ("synset", "link", "target"),
    "remove_relation": ("synset", "link", "target"),
    "add_sense_relation": ("synset", "lemma", "link", "target", "target_lemma"),
    "remove_sense_relation": ("synset", "lemma", "link", "target", "target_lemma"),
    "add_synset": ("synset", "pos", "new"),
    "merge_synset": ("synset", "target"),
}
ALWAYS = ("id", "action", "lexicon", "user", "source", "reason")
ADDITIONS = {"add_sense", "add_form", "add_example", "add_relation", "add_sense_relation",
             "add_synset"}
READING_SCRIPTS = {"hira"}  # forms in these scripts are an entry's readings


@dataclass(slots=True)
class Change:
    """One change to a lexicon.

    Attributes:
        id: unique, e.g. time, user and a counter
        action: one of ``ACTIONS``
        lexicon: the id of the lexicon changed
        synset: the synset changed, or holding the sense changed
        lemma: the written form of the word whose sense is changed
        pos: part of speech, to tell entries with the same lemma apart
        reading: a form of the entry, to tell homographs apart
        entry: the entry id, to name one entry exactly
        old: the value expected before the change; a conflict if it differs
        new: the value wanted (confidence, lemma, form, definition, example)
        link: the relation type, for relations
        target: the other synset, for relations and merges
        target_lemma: the word in ``target``, for a relation between senses
        subtype: what kind of ``other`` relation it is (``dc:type``)
        lang: the language of a definition or example, if not the lexicon's
        script: the script of a form added
        ili: the ILI of a synset added (a CILI id, ``in``, or empty)
        identifier: the local concept id of a synset added (``dc:identifier``)
        user: who made the change
        source: the evidence: a person, a lexicon, a corpus tag
        reason: why
        base: the release the change was made against
    """

    id: str | None = None
    action: str | None = None
    lexicon: str | None = None
    synset: str | None = None
    lemma: str | None = None
    pos: str | None = None
    reading: str | None = None
    entry: str | None = None
    old: str | None = None
    new: str | None = None
    link: str | None = None
    target: str | None = None
    target_lemma: str | None = None
    subtype: str | None = None
    lang: str | None = None
    script: str | None = None
    ili: str | None = None
    identifier: str | None = None
    user: str | None = None
    source: str | None = None
    reason: str | None = None
    base: str | None = None


def dumps(change: Change) -> str:
    """A change as one line of JSON, without the fields it does not use."""
    return json.dumps({k: v for k, v in asdict(change).items() if v is not None},
                      ensure_ascii=False)


def loads(line: str) -> Change:
    """The inverse of ``dumps``.

    Raises:
        ValueError: for a field that is not part of a change record
    """
    d = json.loads(line)
    unknown = set(d) - {f.name for f in fields(Change)}
    if unknown:
        raise ValueError(f"unknown field(s) in change record: {sorted(unknown)}")
    return Change(**d)


def read(path: Path) -> Iterator[Change]:
    """Yield the changes of a JSON Lines file, in order."""
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield loads(line)


def write(path: Path, changes: Iterable[Change]) -> int:
    """Write changes to a JSON Lines file; return how many."""
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for change in changes:
            f.write(dumps(change) + "\n")
            n += 1
    return n


def validate(change: Change) -> list[str]:
    """What is wrong with a change record itself, before it meets a lexicon.

    Returns:
        One message per problem; empty if the record is well formed
    """
    if change.action not in ACTIONS:
        return [f"unknown action {change.action!r}"]
    out = [f"{name} is missing" for name in ALWAYS + ACTIONS[change.action]
           if getattr(change, name) in (None, "")
           and not (name == "new" and change.new == "")]
    if change.action in ADDITIONS and (change.source or "").lower().startswith("model"):
        out.append("a model alone is not a source for an addition")
    return out


def _confidence(sense: Sense) -> float:
    return float(sense.meta.get("confidenceScore", 1.0))


class _Lexicon:
    """A lexicon's objects, indexed for changing."""

    def __init__(self, items: Iterable[Item]) -> None:
        self.header: Lexicon | None = None
        self.entries: list[Entry] = []
        self.synsets: dict[str, Synset] = {}
        self.frames: list[Frame] = []
        self.by_lemma: dict[str, list[Entry]] = {}
        self.emptied: set[int] = set()  # id() of entries a change left without senses
        for item in items:
            if isinstance(item, Lexicon):
                if self.header is not None:
                    raise ValueError("changes apply to one lexicon at a time")
                self.header = item
            elif isinstance(item, Entry):
                self._add_entry(item)
            elif isinstance(item, Synset):
                self.synsets[str(item.id)] = item
            elif isinstance(item, Frame):
                self.frames.append(item)
            else:
                raise TypeError(f"{type(item).__name__} is not part of a lexicon")
        if self.header is None:
            raise ValueError("no Lexicon among the items")
        numbers = [int(m.group(1)) for e in self.entries
                   if (m := re.search(r"(\d+)$", e.id or ""))]
        self.next_number = max(numbers, default=-1) + 1
        self.sense_ids = {s.id for e in self.entries for s in e.senses}

    def _add_entry(self, entry: Entry) -> None:
        self.entries.append(entry)
        self.by_lemma.setdefault(str(entry.lemma), []).append(entry)

    def items(self) -> Iterator[Item]:
        """The lexicon as items again, without the entries left empty."""
        assert self.header is not None
        yield self.header
        yield from (e for e in self.entries if e.senses or id(e) not in self.emptied)
        yield from self.synsets.values()
        yield from self.frames

    def entries_for(self, c: Change, lemma: str | None = None) -> list[Entry]:
        """The entries a change names by lemma, and pos, reading or id if given."""
        return [e for e in self.by_lemma.get(lemma or c.lemma or "", [])
                if (c.pos is None or e.pos == c.pos)
                and (c.entry is None or e.id == c.entry)
                and (c.reading is None or any(f.form == c.reading for f in e.forms))]

    def senses_for(self, c: Change) -> list[tuple[Entry, Sense]]:
        """The senses a change names: its lemma's senses in its synset."""
        return [(e, s) for e in self.entries_for(c) for s in e.senses if s.synset == c.synset]

    def new_entry(self, lemma: str, pos: str) -> Entry:
        """Add an entry, with an id made like the others'."""
        first = self.entries[0].id if self.entries else f"{self.header.id}-"  # type: ignore[union-attr]
        stem = re.sub(r"\d+$", "", first or "")
        stem = re.sub(r"-[a-z]-$", f"-{pos}-", stem)
        entry = Entry(lemma=lemma, pos=pos, id=f"{stem}{self.next_number}")
        self.next_number += 1
        self._add_entry(entry)
        return entry

    def new_sense(self, entry: Entry, synset: Synset) -> Sense:
        """Add a sense to an entry, with an id made like the others'."""
        base = f"{synset.id}-{(entry.id or '').rsplit('-', 1)[-1]}"
        sid, n = base, 1
        while sid in self.sense_ids:
            n += 1
            sid = f"{base}-{n}"
        sense = Sense(synset=synset.id, id=sid)
        self.sense_ids.add(sid)
        entry.senses.append(sense)
        if synset.members is not None:
            synset.members = f"{synset.members} {sid}".strip()
        return sense

    def drop_sense(self, entry: Entry, sense: Sense) -> None:
        """Take a sense off its entry and out of its synset's members."""
        entry.senses.remove(sense)
        if not entry.senses:
            self.emptied.add(id(entry))
        synset = self.synsets.get(str(sense.synset))
        if synset is not None and synset.members:
            synset.members = " ".join(m for m in synset.members.split() if m != sense.id)


def _readings(entry: Entry) -> frozenset[str]:
    return frozenset(str(f.form) for f in entry.forms if f.script in READING_SCRIPTS)


def _sense(lex: _Lexicon, c: Change) -> str | None:
    """Changes to senses that exist: remove, keep, set confidence, rename."""
    found = lex.senses_for(c)
    if not found:
        return f"no sense of {c.lemma} in {c.synset}"
    if c.action == "keep_sense":
        return None
    if c.action == "remove_sense":
        for entry, sense in found:
            lex.drop_sense(entry, sense)
        return None
    if c.action == "set_confidence":
        if c.old is not None and any(_confidence(s) != float(c.old) for _, s in found):
            return f"confidence of {c.lemma} in {c.synset} is not {c.old}"
        for _, sense in found:
            sense.meta["confidenceScore"] = str(c.new)
        return None
    for entry, sense in found:
        _rename(lex, entry, sense, str(c.new))
    return None


def _rename(lex: _Lexicon, old: Entry, sense: Sense, new: str) -> None:
    """Give one sense of ``old`` the written form ``new``.

    The sense goes to an entry with that lemma and part of speech whose
    readings match (or where either has none), which also gains the old
    entry's other forms.  Failing that, the old entry is renamed if it
    has no other sense, or copied under the new lemma.  A sense the
    target already has is dropped.
    """
    old.senses.remove(sense)
    target = next((e for e in lex.by_lemma.get(new, [])
                   if e.pos == old.pos and e is not old
                   and (not _readings(e) or not _readings(old)
                        or _readings(e) == _readings(old))), None)
    if target is None:
        forms = [f for f in old.forms if f.form != new]
        if old.senses:
            target = Entry(lemma=new, pos=old.pos, id=f"{old.id}-r", script=old.script,
                           meta=dict(old.meta), tags=list(old.tags), forms=forms,
                           pronunciations=list(old.pronunciations))
            lex._add_entry(target)
        else:
            lex.by_lemma[str(old.lemma)].remove(old)
            old.lemma, old.forms = new, forms
            lex.by_lemma.setdefault(new, []).append(old)
            target = old
    else:
        known = {new} | {f.form for f in target.forms}
        target.forms += [f for f in old.forms if f.form not in known]
        if not old.senses:
            lex.emptied.add(id(old))
    if any(s.synset == sense.synset for s in target.senses):
        synset = lex.synsets.get(str(sense.synset))
        if synset is not None and synset.members:
            synset.members = " ".join(m for m in synset.members.split() if m != sense.id)
    else:
        target.senses.append(sense)


def _add_sense(lex: _Lexicon, c: Change) -> str | None:
    synset = lex.synsets.get(c.synset or "")
    if synset is None:
        return f"no synset {c.synset}"
    if lex.senses_for(c):
        return f"{c.lemma} is already in {c.synset}"
    pos = c.pos or str(synset.pos)
    entries = [e for e in lex.entries_for(c) if e.pos == pos]
    if len(entries) > 1:
        return f"{len(entries)} entries for {c.lemma} ({pos}): give reading or entry"
    if not entries and (c.entry or c.reading):
        return f"no entry {c.entry or c.reading} for {c.lemma} ({pos})"
    entry = entries[0] if entries else lex.new_entry(str(c.lemma), pos)
    sense = lex.new_sense(entry, synset)
    if c.new is not None:
        sense.meta["confidenceScore"] = c.new
    return None


def _add_form(lex: _Lexicon, c: Change) -> str | None:
    entries = lex.entries_for(c)
    if not entries:
        return f"no entry {c.lemma} ({c.pos})"
    if c.action == "remove_form":
        if not any(f.form == c.old for e in entries for f in e.forms):
            return f"{c.lemma} ({c.pos}) has no form {c.old}"
        for e in entries:
            e.forms = [f for f in e.forms if f.form != c.old]
        return None
    if all(c.new == e.lemma or any(f.form == c.new for f in e.forms) for e in entries):
        return f"{c.lemma} ({c.pos}) already has the form {c.new}"
    for e in entries:
        if c.new != e.lemma and not any(f.form == c.new for f in e.forms):
            e.forms.append(Form(form=c.new, script=c.script))
    return None


def _text(lex: _Lexicon, c: Change) -> str | None:
    """Set a definition or add an example."""
    synset = lex.synsets.get(c.synset or "")
    if synset is None:
        return f"no synset {c.synset}"
    if c.action == "add_example":
        if any(x.text == c.new and x.lang == c.lang for x in synset.examples):
            return f"{c.synset} already has this example"
        synset.examples.append(Text(text=c.new, lang=c.lang))
        return None
    current = next((d for d in synset.definitions if d.lang == c.lang), None)
    if current is None:
        if c.old:
            return f"{c.synset} has no definition, expected: {c.old}"
        synset.definitions.append(Text(text=c.new, lang=c.lang))
    elif c.old is None or current.text != c.old:
        return f"definition of {c.synset} is not the one expected: {current.text}"
    else:
        current.text = c.new
    return None


def _relation(lex: _Lexicon, c: Change) -> str | None:
    synset = lex.synsets.get(c.synset or "")
    if synset is None:
        return f"no synset {c.synset}"
    have = [r for r in synset.relations if r.link == c.link and r.target == c.target]
    if c.action == "remove_relation":
        if not have:
            return f"no {c.link} from {c.synset} to {c.target}"
        synset.relations = [r for r in synset.relations if r not in have]
    elif have:
        return f"{c.synset} already has {c.link} to {c.target}"
    else:
        synset.relations.append(Relation(link=c.link, target=c.target))
    return None


def _sense_relation(lex: _Lexicon, c: Change) -> str | None:
    """Add or remove a relation between two senses, each named by synset and lemma."""
    sources = lex.senses_for(c)
    targets = [s for e in lex.by_lemma.get(c.target_lemma or "", [])
               for s in e.senses if s.synset == c.target]
    if not sources or not targets:
        missing = (c.lemma, c.synset) if not sources else (c.target_lemma, c.target)
        return "no sense of {} in {}".format(*missing)
    meta = {"dc:type": c.subtype} if c.subtype else {}
    ids = {t.id for t in targets}

    def same(r: SenseRelation) -> bool:
        return r.link == c.link and r.target in ids and r.meta == meta

    have = any(same(r) for _, s in sources for r in s.relations)
    if c.action == "remove_sense_relation":
        if not have:
            return f"no {c.link} from {c.lemma} to {c.target_lemma}"
        for _, s in sources:
            s.relations = [r for r in s.relations if not same(r)]
    elif have:
        return f"{c.lemma} already has {c.link} to {c.target_lemma}"
    else:
        for _, s in sources:
            s.relations += [SenseRelation(link=c.link, target=t.id, meta=dict(meta))
                            for t in targets]
    return None


def _add_synset(lex: _Lexicon, c: Change) -> str | None:
    if c.synset in lex.synsets:
        return f"synset {c.synset} exists"
    synset = Synset(id=c.synset, pos=c.pos, ili=c.ili or "",
                    definitions=[Text(text=c.new, lang=c.lang)])
    if c.identifier:
        synset.meta["dc:identifier"] = c.identifier
    lex.synsets[str(c.synset)] = synset
    return None


def _merge_synset(lex: _Lexicon, c: Change) -> str | None:
    """Move the senses and relations of ``synset`` to ``target`` and drop it."""
    old, new = lex.synsets.get(c.synset or ""), lex.synsets.get(c.target or "")
    if old is None or new is None:
        return f"no synset {c.synset if old is None else c.target}"
    if old is new:
        return f"cannot merge {c.synset} with itself"
    for entry in lex.entries:
        mine = [s for s in entry.senses if s.synset == old.id]
        for sense in mine:
            if any(s.synset == new.id for s in entry.senses):
                lex.drop_sense(entry, sense)
            else:
                sense.synset = new.id
                if new.members is not None:
                    new.members = f"{new.members} {sense.id}".strip()
    have = {(r.link, r.target) for r in new.relations}
    new.relations += [r for r in old.relations
                      if r.target != new.id and (r.link, r.target) not in have]
    del lex.synsets[str(old.id)]
    for synset in lex.synsets.values():
        seen = set()
        kept = []
        for r in synset.relations:
            if r.target == old.id:
                r.target = new.id
            if r.target != synset.id and (r.link, r.target) not in seen:
                kept.append(r)
            seen.add((r.link, r.target))
        synset.relations = kept
    return None


HANDLERS = {
    "add_sense": _add_sense, "remove_sense": _sense, "keep_sense": _sense,
    "set_confidence": _sense, "rename_lemma": _sense, "add_form": _add_form,
    "remove_form": _add_form, "add_sense_relation": _sense_relation,
    "remove_sense_relation": _sense_relation,
    "set_definition": _text, "add_example": _text, "add_relation": _relation,
    "remove_relation": _relation, "add_synset": _add_synset, "merge_synset": _merge_synset,
}


def apply(items: Iterable[Item], changes: Iterable[Change]) -> tuple[list[Item], list[str]]:
    """Apply changes, in order, to the model objects of one lexicon.

    The objects are changed in place.  A change that is malformed or
    does not fit the lexicon is not made, and is reported.

    Args:
        items: a ``Lexicon`` and its entries, synsets and frames
        changes: the change records, oldest first

    Returns:
        the lexicon's items after the changes, and one line per conflict

    Raises:
        ValueError: if the items are not exactly one lexicon
        TypeError: if an item cannot be part of a lexicon (a ``Gloss`` or ``Row``)
    """
    lex = _Lexicon(items)
    conflicts = []
    seen: set[str] = set()
    for c in changes:
        problems = validate(c)
        if c.id in seen:
            problems.append("id used twice")
        seen.add(c.id or "")
        if not problems and c.lexicon != lex.header.id:  # type: ignore[union-attr]
            problems.append(f"is for lexicon {c.lexicon}, not {lex.header.id}")  # type: ignore[union-attr]
        if not problems:
            problem = HANDLERS[str(c.action)](lex, c)
            problems = [problem] if problem else []
        conflicts += [f"{c.id}: {c.action}: {p}" for p in problems]
    return list(lex.items()), conflicts
