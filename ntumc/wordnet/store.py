"""Read the wordnet database into model objects and write them back.

Reading is lossless: every row of every table comes out, either inside
a ``Synset``, ``Gloss`` or ``Entry`` or as a ``Row``.  ``compare`` checks
that two databases hold the same rows (as multisets: the tables have no
row order) and the same schema.
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable, Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

from .model import (
    Comment,
    Entry,
    Gloss,
    Item,
    Relation,
    Row,
    Sense,
    SenseRelation,
    SenseXLink,
    Synset,
    Text,
    XLink,
)

# table -> (class, columns naming the parent, {column: field} where they differ)
CHILDREN: dict[str, tuple[type, tuple[str, ...], dict[str, str]]] = {
    "synlink": (Relation, ("synset1",), {"synset2": "target"}),
    "xlink": (XLink, ("synset",), {}),
    "synset_comment": (Comment, ("synset",), {}),
    "synset_def": (Text, ("synset", "lang"), {"def": "text"}),
    "synset_ex": (Text, ("synset", "lang"), {"def": "text"}),
    "senslink": (SenseRelation, ("synset1", "wordid1"), {}),
    "xlinks": (SenseXLink, ("synset", "wordid"), {}),
    "sense": (Sense, ("wordid",), {}),
}
PARENTS: dict[str, tuple[type, dict[str, str]]] = {
    "synset": (Synset, {"synset": "id"}),
    "word": (Entry, {}),
}
MODELLED = set(CHILDREN) | set(PARENTS)


def connect(path: Path, readonly: bool = True) -> sqlite3.Connection:
    """Open a database, read-only unless told otherwise."""
    uri = f"file:{path}?mode=ro" if readonly else f"file:{path}"
    return sqlite3.connect(uri, uri=True)


def tables(con: sqlite3.Connection) -> list[str]:
    """The tables of a database, in creation order."""
    return [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY rowid")]


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    """The columns of a table."""
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def schema(con: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """(type, name, sql) of every table, index and trigger, in creation order."""
    return list(con.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY rowid"))


def _field_names(cls: type) -> list[str]:
    return [f.name for f in fields(cls) if f.type.startswith("Value")]


def _check_columns(con: sqlite3.Connection, table: str, cls: type,
                   rename: dict[str, str], parent: tuple[str, ...] = ()) -> list[str]:
    """The table's columns, after checking the class has a field for each."""
    cols = columns(con, table)
    have = set(_field_names(cls))
    missing = [c for c in cols if c not in parent and rename.get(c, c) not in have]
    if missing:
        raise ValueError(f"{table}: no model field for column(s) {missing}")
    return cols


def _children(con: sqlite3.Connection, table: str) -> dict[tuple, list[Any]]:
    """Parent key -> the child objects of that table, in rowid order."""
    cls, parent, rename = CHILDREN[table]
    cols = _check_columns(con, table, cls, rename, parent)
    keep = [(i, rename.get(c, c)) for i, c in enumerate(cols) if c not in parent]
    key = [cols.index(p) for p in parent]
    out: dict[tuple, list[Any]] = defaultdict(list)
    for row in con.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
        out[tuple(row[i] for i in key)].append(cls(**{name: row[i] for i, name in keep}))
    return out


def _orphans(table: str, left: dict[tuple, list[Any]]) -> Iterator[Row]:
    """Child objects whose parent does not exist, as rows of their table."""
    cls, parent, rename = CHILDREN[table]
    back = {v: k for k, v in rename.items()}
    for key, objs in left.items():
        for obj in objs:
            values = dict(zip(parent, key, strict=True))
            for name in _field_names(cls):
                values[back.get(name, name)] = getattr(obj, name)
            yield Row(table, values)


def read(path: Path, history: bool = True) -> Iterator[Item]:
    """Yield every row of the database as model objects.

    Order: synsets, glosses, entries, then rows (unmodelled tables,
    orphans and, with ``history``, the ``*_log`` tables).

    Args:
        path: the wordnet database
        history: also yield the ``*_log`` tables

    Yields:
        Synset, Gloss, Entry and Row objects
    """
    con = connect(path)
    kids = {t: _children(con, t) for t in CHILDREN}

    cls, rename = PARENTS["synset"]
    cols = [rename.get(c, c) for c in _check_columns(con, "synset", cls, rename)]
    seen = set()
    for row in con.execute("SELECT * FROM synset ORDER BY synset"):
        s = Synset(**dict(zip(cols, row, strict=True)))
        if s.id in seen:  # a second row for the same id cannot own the children
            yield Row("synset", dict(zip(columns(con, "synset"), row, strict=True)))
            continue
        seen.add(s.id)
        s.relations = kids["synlink"].pop((s.id,), [])
        s.xlinks = kids["xlink"].pop((s.id,), [])
        s.comments = kids["synset_comment"].pop((s.id,), [])
        yield s

    defs, exes = kids["synset_def"], kids["synset_ex"]
    for key in sorted(set(defs) | set(exes), key=lambda k: (str(k[0]), str(k[1]))):
        yield Gloss(key[0], key[1], defs.pop(key, []), exes.pop(key, []))

    cls, rename = PARENTS["word"]
    cols = _check_columns(con, "word", cls, rename)
    for row in con.execute("SELECT * FROM word ORDER BY lang, lemma, pos, wordid"):
        e = Entry(**dict(zip(cols, row, strict=True)))
        e.senses = kids["sense"].pop((e.wordid,), [])
        for s in e.senses:
            s.relations = kids["senslink"].pop((s.synset, e.wordid), [])
            s.xlinks = kids["xlinks"].pop((s.synset, e.wordid), [])
        yield e

    for table in CHILDREN:
        yield from _orphans(table, kids[table])
    for table in tables(con):
        if table in MODELLED or (table.endswith("_log") and not history):
            continue
        cols = columns(con, table)
        for row in con.execute(f'SELECT * FROM "{table}" ORDER BY rowid'):
            yield Row(table, dict(zip(cols, row, strict=True)))
    con.close()


def _flat(item: Item) -> Iterator[tuple[str, dict[str, Any]]]:
    """(table, {column: value}) for every database row inside a model object."""

    def row(table: str, obj: Any, parent: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        cls, _, rename = CHILDREN[table]
        back = {v: k for k, v in rename.items()}
        return table, parent | {back.get(n, n): getattr(obj, n) for n in _field_names(cls)}

    if isinstance(item, Row):
        yield item.table, item.values
    elif isinstance(item, Synset):
        yield "synset", {"synset": item.id, "pos": item.pos, "name": item.name,
                         "src": item.src, "usr": item.usr}
        for table, objs in (("synlink", item.relations), ("xlink", item.xlinks),
                            ("synset_comment", item.comments)):
            key = "synset1" if table == "synlink" else "synset"
            for obj in objs:
                yield row(table, obj, {key: item.id})
    elif isinstance(item, Gloss):
        for table, objs in (("synset_def", item.definitions), ("synset_ex", item.examples)):
            for obj in objs:
                yield row(table, obj, {"synset": item.synset, "lang": item.lang})
    else:
        yield "word", {n: getattr(item, n) for n in _field_names(Entry)}
        for s in item.senses:
            yield row("sense", s, {"wordid": item.wordid})
            for r in s.relations:
                yield row("senslink", r, {"synset1": s.synset, "wordid1": item.wordid})
            for x in s.xlinks:
                yield row("xlinks", x, {"synset": s.synset, "wordid": item.wordid})


def write(path: Path, ddl: Iterable[tuple[str, str, str]], items: Iterable[Item]) -> None:
    """Create a database from a schema and model objects.

    Tables are created first, then filled, then indexes and triggers are
    added, so that loading writes nothing to the ``*_log`` tables.

    Args:
        path: the database to create (must not exist)
        ddl: (type, name, sql) as returned by ``schema``
        items: the model objects
    """
    if path.exists():
        raise FileExistsError(path)
    ddl = list(ddl)
    con = connect(path, readonly=False)
    con.execute("PRAGMA foreign_keys = OFF")
    for kind, _, sql in ddl:
        if kind == "table":
            con.execute(sql)
    batch: dict[tuple[str, tuple[str, ...]], list[tuple]] = defaultdict(list)

    def flush() -> None:
        for (table, cols), rows in batch.items():
            marks = ",".join("?" * len(cols))
            names = ",".join(f'"{c}"' for c in cols)
            con.executemany(f'INSERT INTO "{table}" ({names}) VALUES ({marks})', rows)
        batch.clear()

    n = 0
    for item in items:
        for table, values in _flat(item):
            batch[(table, tuple(values))].append(tuple(values.values()))
            n += 1
        if n >= 200_000:
            flush()
            n = 0
    flush()
    for kind, _, sql in ddl:
        if kind != "table":
            con.execute(sql)
    con.commit()
    con.close()


def compare(a: Path, b: Path) -> list[str]:
    """Differences between two databases: schema, and rows of each table.

    Rows are compared as multisets, so a duplicated row must be
    duplicated on both sides.

    Returns:
        One line per difference; empty when the databases are equal
    """
    out = []
    ca, cb = connect(a), connect(b)
    sa, sb = set(schema(ca)), set(schema(cb))
    out += [f"schema only in {a.name}: {t} {n}" for t, n, _ in sorted(sa - sb)]
    out += [f"schema only in {b.name}: {t} {n}" for t, n, _ in sorted(sb - sa)]
    cb.close()
    ca.execute("ATTACH ? AS b", (f"file:{b}?mode=ro",))
    for table in tables(ca):
        cols = ",".join(f'"{c}"' for c in columns(ca, table))
        if not ca.execute("SELECT 1 FROM b.sqlite_master WHERE name = ?", (table,)).fetchone():
            continue
        q = (f'SELECT count(*) FROM (SELECT {cols}, count(*) FROM {{x}}."{table}" GROUP BY {cols} '
             f'EXCEPT SELECT {cols}, count(*) FROM {{y}}."{table}" GROUP BY {cols})')
        for x, y, name in (("main", "b", a.name), ("b", "main", b.name)):
            n = ca.execute(q.format(x=x, y=y)).fetchone()[0]
            if n:
                out.append(f"{table}: {n} distinct row(s) only in {name}")
    ca.close()
    return out
