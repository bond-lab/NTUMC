# The wordnet as Python objects, and as JSON Lines

`ntumc.wordnet` reads the NTU-MC wordnet database (`wn-ntumc.db`) into
plain dataclasses, writes them as JSON Lines and loads them back into a
database.  The round trip is lossless: every row of every table and the
whole schema come back, and `check` proves it.

```
python -m ntumc.wordnet dump  build/wn-ntumc.db OUTDIR [--no-history]
python -m ntumc.wordnet load  INDIR NEW.db
python -m ntumc.wordnet check build/wn-ntumc.db
```

On the server copy frozen on 2026-11-13 (1,229,348 senses, 121,016
synsets, 324,648 log rows) `check` reports `round trip: identical`.  It
takes about two and a half minutes and the dump is 400 MB, of which the
history is 128 MB.

## The model

| object | tables | one per |
|---|---|---|
| `Synset` | `synset`, with `synlink`, `xlink`, `synset_comment` | concept, shared by all languages |
| `Gloss` | `synset_def`, `synset_ex` | synset and language |
| `Entry` | `word`, with `sense`, and under each sense `senslink`, `xlinks` | word |
| `Row` | everything else | row |

A `Row` carries a table name and the row's values.  It is used for the
`*_log` history, the small tables the model does not interpret (`meta`,
`pos_def`, `link_def`), and orphans: rows whose parent is missing (in
the frozen copy, 4 sense links, 12 synset comments and 15 sense
cross-links).  Reading fails if a table has a column the model has no
field for, so a schema change cannot silently lose data.

## The files

```
schema.sql        tables, indexes and triggers, to rebuild the database
concepts.jsonl    one synset per line
LANG.jsonl        for each language: its glosses, then its entries
other.jsonl       unmodelled tables and orphans
history.jsonl     the *_log tables
```

Each line is one object with a `kind`; `None` and empty lists are left
out, an empty string is kept.

```json
{"kind": "entry", "wordid": 402112, "lang": "jpn", "lemma": "$", "pos": "n",
 "senses": [{"synset": "06821581-n", "lang": "jpn", "src": "jpn", "confidence": 1.0}]}
```

Loading creates the tables, fills them, and only then adds the indexes
and triggers, so nothing is written to the logs.  Rows are compared as
multisets, because the tables have no row order and a few rows are
duplicated.

## Not done yet

* WN-LMF XML in and out of the same model.
* Applying change records (below) to a base.

## Change records

The master copy of a wordnet is a base release plus an ordered list of
changes.  A release applies the list and its output is the next base.
One record per line, in the order made; the editor appends, nothing is
rewritten.

```json
{"id": "2026-11-13T10:02:11Z-fcbond-1", "action": "remove_sense",
 "lexicon": "wnja", "synset": "02084071-n", "lemma": "イヌ", "pos": "n",
 "user": "fcbond", "source": "native check", "reason": "not used for this meaning",
 "base": "wnja-2.1"}
```

| field | meaning |
|---|---|
| `id` | unique: time, user and a counter |
| `action` | see below |
| `lexicon`, `synset`, and `lemma` + `pos` or a relation or text | what is changed |
| `old`, `new` | for changes of value: the value expected and the value wanted |
| `user`, `source`, `reason` | who, on what evidence (a person, a lexicon, a corpus tag), and why |
| `base` | the release the change was made against |

Actions: `add_sense`, `remove_sense`, `set_confidence`, `rename_lemma`,
`add_form`, `set_definition`, `add_example`, `add_relation`,
`remove_relation`, `add_synset`, `merge_synset`; more can be added as
needed.  These cover the
`action` values already used in `wnja/corrections/senses.tsv`
(`remove`, `lower`, `rename`, `keep`, `add`), `definitions.tsv` and
`forms.tsv`.

A record with `old` applies only if the value is still `old`; otherwise
the release stops and reports a conflict for a person to settle.
`source` is required, and a model alone is not a source for an
addition.

## Local concept ids

Concepts we share across languages before CILI has them get a local
identifier, `ntumc00001`.  The registry is its own repository,
`omw-mul-ntumc` (`registry.tsv`, checked by `check_registry.py`):

```
local_id    pos  definition  proposed_by  date  cili  status
```

* `local_id` is `ntumc` and five digits; it never changes and is never
  reused.  The prefix keeps our ids apart from other projects' when
  several shared lexicons are merged.
* The definition is in English and meets the CILI rule (at least 20
  characters or five words).
* `status` is `proposed`, `submitted`, `granted` or `withdrawn`.
* In WN-LMF a synset for a local concept has `ili="in"`, an
  `ILIDefinition`, and `dc:identifier="ntumc00001"`.  The local id never
  goes in the `ili` attribute, which must hold a CILI id, `in` or
  nothing.  Cygnet already merges synsets across lexicons on
  `dc:identifier`.
* When CILI grants an id, it is entered in `cili`, and builds write that
  id in `ili` from then on, keeping the `dc:identifier`.
* The concepts themselves (definition, relations) live in one shared
  lexicon with `language="mul"`, as omw-pronoun does; the language
  lexicons only add words.
