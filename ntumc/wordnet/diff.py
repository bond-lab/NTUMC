"""The change records that turn one version of a lexicon into another.

``diff`` compares two versions by what they say, not by their
identifiers or order: which word is in which synset and how surely,
its forms, the definitions, examples and relations.  It is how an
existing build becomes a change log: build as before one last time,
and diff the result against the last release.

Not every difference has a change record (entry and sense metadata).
``residual`` applies the records to the old version and lists what
still differs from the new one, so nothing is passed over in silence.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from . import changes
from .changes import READING_SCRIPTS, Change
from .model import Entry, Item, Synset

Fact = tuple[Any, ...]


def _squash(text: Any) -> str:
    return " ".join(str(text or "").split())


def facts(items: Iterable[Item]) -> Counter[Fact]:
    """What a lexicon says, as tuples free of identifiers and order.

    Args:
        items: a ``Lexicon`` and its entries and synsets

    Returns:
        A multiset of facts; the first element of each names its kind:
        ``sense``, ``conf``, ``form``, ``def``, ``ex``, ``rel``, ``srel``,
        ``count``, ``tag``, ``synset``, and ``meta`` for what has no
        change record
    """
    items = list(items)
    where = {s.id: (s.synset, e.lemma) for e in items if isinstance(e, Entry) for s in e.senses}
    out: Counter[Fact] = Counter()
    for i in items:
        if isinstance(i, Entry):
            for s in i.senses:
                out[("sense", s.synset, i.lemma, i.pos)] += 1
                out[("conf", s.synset, i.lemma, i.pos,
                     float(s.meta.get("confidenceScore", 1.0)))] += 1
                for r in s.relations:
                    out[("srel", s.synset, i.lemma, r.link, *where.get(r.target, (r.target, None)),
                         r.meta.get("dc:type"))] += 1
                for c in s.counts:
                    out[("count", s.synset, i.lemma, i.pos, c.meta.get("dc:source"), c.text)] += 1
                rest = {k: v for k, v in s.meta.items() if k != "confidenceScore"}
                if rest or s.lexicalized or s.adjposition or s.subcat or s.examples:
                    out[("meta", "sense", s.synset, i.lemma, tuple(sorted(rest.items())),
                         s.lexicalized, s.adjposition, s.subcat,
                         tuple(_squash(x.text) for x in s.examples))] += 1
            for f in i.forms:
                out[("form", i.lemma, i.pos, f.form, f.script)] += 1
            for t in i.tags:
                out[("tag", i.lemma, i.pos, t.category, t.text)] += 1
            if i.meta or i.script or i.pronunciations:
                out[("meta", "entry", i.lemma, i.pos, i.script, tuple(sorted(i.meta.items())),
                     tuple((p.text, p.notation, p.variety) for p in i.pronunciations))] += 1
        elif isinstance(i, Synset):
            out[("synset", i.id, i.pos, i.ili, i.meta.get("dc:identifier"))] += 1
            for d in i.definitions:
                out[("def", i.id, d.lang, _squash(d.text))] += 1
            for e in i.examples:
                out[("ex", i.id, e.lang, _squash(e.text))] += 1
            for r in i.relations:
                out[("rel", i.id, r.link, r.target)] += 1
            rest = {k: v for k, v in i.meta.items() if k != "dc:identifier"}
            if rest or i.lexicalized or i.lexfile:
                out[("meta", "synset", i.id, tuple(sorted(rest.items())),
                     i.lexicalized, i.lexfile)] += 1
    return out


def _readings(entry: Entry) -> list[str]:
    return [str(f.form) for f in entry.forms if f.script in READING_SCRIPTS]


def diff(old: Iterable[Item], new: Iterable[Item], **common: str) -> list[Change]:
    """The changes that turn ``old`` into ``new``, as far as records can.

    Args:
        old: the earlier version of a lexicon
        new: the later version
        **common: fields for every record: ``lexicon``, ``user``,
            ``source``, ``reason``, ``base``

    Returns:
        Change records in an order that applies: new synsets, senses,
        emptied synsets,
        confidence, counts, forms, tags, texts, relations
    """
    old, new = list(old), list(new)
    a, b = facts(old), facts(new)
    gone, come = a - b, b - a
    prefix = common.get("base") or common.get("lexicon") or "diff"
    out: list[Change] = []

    def add(action: str, **kw: Any) -> None:
        out.append(Change(id=f"{prefix}-diff-{len(out) + 1}", action=action, **common, **kw))

    def of(kind: str, side: Counter[Fact]) -> list[Fact]:
        return sorted((f for f in side if f[0] == kind), key=lambda f: tuple(map(str, f)))

    homographs = Counter((e.lemma, e.pos) for e in old if isinstance(e, Entry))
    new_entries: dict[tuple[Any, Any], list[Entry]] = {}
    for e in new:
        if isinstance(e, Entry):
            new_entries.setdefault((e.lemma, e.pos), []).append(e)

    def reading(lemma: Any, pos: Any, has: Any) -> str | None:
        """A reading to pick out one of several old entries for a lemma."""
        if homographs[(lemma, pos)] < 2:
            return None
        for e in new_entries.get((lemma, pos), []):
            if has(e) and _readings(e):
                return _readings(e)[0]
        return None

    new_defs = {f[1:3]: f[3] for f in of("def", b)}
    for _, sid, pos, ili, ident in of("synset", come):
        if not any(f[1] == sid for f in of("synset", gone)):
            add("add_synset", synset=sid, pos=pos, ili=ili, identifier=ident,
                new=new_defs.get((sid, None), ""))
            come[("def", sid, None, new_defs.get((sid, None), ""))] -= 1
    for _, synset, lemma, pos in of("sense", gone):
        add("remove_sense", synset=synset, lemma=lemma, pos=pos)
    dropped = {f[1] for f in of("synset", gone)} - {f[1] for f in of("synset", come)}
    for sid in sorted(dropped):
        add("remove_synset", synset=sid)
    added = set()
    confidence = {f[1:4]: f[4] for f in of("conf", b)}
    for _, synset, lemma, pos in of("sense", come):
        conf = confidence.get((synset, lemma, pos), 1.0)
        add("add_sense", synset=synset, lemma=lemma, pos=pos,
            reading=reading(lemma, pos, lambda e, s=synset: any(x.synset == s for x in e.senses)),
            new=None if conf == 1.0 else str(conf))
        added.add((synset, lemma, pos))
    was = {f[1:4]: f[4] for f in of("conf", a)}
    for _, synset, lemma, pos, conf in of("conf", come):
        if (synset, lemma, pos) not in added and (synset, lemma, pos) in was:
            add("set_confidence", synset=synset, lemma=lemma, pos=pos,
                old=str(was[(synset, lemma, pos)]), new=str(conf))
    counted = {f[1:5]: f[5] for f in of("count", gone)}
    for _, synset, lemma, pos, corpus, n in of("count", come):
        add("set_count", synset=synset, lemma=lemma, pos=pos, corpus=corpus, new=n,
            old=counted.pop((synset, lemma, pos, corpus), None))
    for (synset, lemma, pos, corpus), n in counted.items():
        if ("sense", synset, lemma, pos) not in gone:
            add("set_count", synset=synset, lemma=lemma, pos=pos, corpus=corpus, new="0", old=n)
    for _, lemma, pos, form, _script in of("form", gone):
        if (lemma, pos) in new_entries:
            add("remove_form", lemma=lemma, pos=pos, old=form)
    for _, lemma, pos, form, script in of("form", come):
        add("add_form", lemma=lemma, pos=pos, new=form, script=script,
            reading=reading(lemma, pos, lambda e, f=form: any(
                x.form == f for x in e.forms) and _readings(e) != [f]))
    tagged = {f[1:4]: f[4] for f in of("tag", gone)}
    for _, lemma, pos, category, text in of("tag", come):
        add("set_tag", lemma=lemma, pos=pos, category=category, new=text,
            old=tagged.pop((lemma, pos, category), ""))
    for (lemma, pos, category), text in tagged.items():
        if (lemma, pos) in new_entries:
            add("set_tag", lemma=lemma, pos=pos, category=category, new="", old=text)
    old_defs = {f[1:3]: f[3] for f in of("def", gone)}
    for _, sid, lang, text in of("def", come):
        if come[("def", sid, lang, text)] > 0:
            add("set_definition", synset=sid, lang=lang, old=old_defs.get((sid, lang)), new=text)
    for _, sid, lang, text in of("ex", come):
        add("add_example", synset=sid, lang=lang, new=text)
    for side, action in ((gone, "remove_relation"), (come, "add_relation")):
        for _, sid, link, target in of("rel", side):
            if sid not in dropped and target not in dropped:
                add(action, synset=sid, link=link, target=target)
    for side, action in ((gone, "remove_sense_relation"), (come, "add_sense_relation")):
        for _, synset, lemma, link, target, target_lemma, subtype in of("srel", side):
            if target_lemma is not None:
                add(action, synset=synset, lemma=lemma, link=link, target=target,
                    target_lemma=target_lemma, subtype=subtype)
    return out


def residual(old: Iterable[Item], new: Iterable[Item],
             records: Iterable[Change]) -> tuple[list[str], Counter[Fact], Counter[Fact]]:
    """What still differs after applying ``records`` to ``old``.

    Args:
        old: the earlier version (its objects are changed in place)
        new: the later version
        records: the change records, as from ``diff``

    Returns:
        the conflicts, the facts only in the result, the facts only in ``new``
    """
    items, conflicts = changes.apply(old, records)
    got, want = facts(items), facts(new)
    return conflicts, got - want, want - got
