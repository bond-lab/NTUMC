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

## WN-LMF

The same classes hold a WN-LMF lexicon, so a release file can be read,
changed and written with nothing lost.

```
python -m ntumc.wordnet lmf2jsonl WN.xml WN.jsonl
python -m ntumc.wordnet jsonl2lmf WN.jsonl WN.xml
python -m ntumc.wordnet check-lmf WN.xml
```

`check-lmf` reads the XML, writes JSON Lines, reads that back, writes
XML and compares it with the original: same elements in the same order,
same attributes, same text.  Layout, attribute order and XML comments
are not compared.  It reports `round trip: identical` for

| file | items |
|---|---|
| `wnja-2.1.xml` | 158,216 |
| `cow-1.1.xml` | 128,850 |
| `wnb-id-1.5.xml`, `wnb-zsm-1.5.xml` | 85,985 and 70,279 |
| `wn-ntumc-jpn.xml` (the wnja source) | 221,541 |
| `english-wordnet-2025-plus.xml` | 282,479 |
| all omw-pronoun and omw-kinship files | 3,919 files |

A file starts with a `lexicon` line, followed by its entries, synsets
and frames in file order:

```json
{"kind": "entry", "lemma": "可能", "pos": "a", "id": "wnja-a-0",
 "senses": [{"synset": "wnja-00051373-a", "id": "wnja-00051373-a-0",
             "counts": [{"text": "1", "meta": {"dc:source": "JSemCor"}}]}],
 "tags": [{"text": "na", "category": "adjective-class"}],
 "forms": [{"form": "カノウ", "script": "kana"}]}
```

* The `Lemma` element is folded into the entry (`lemma`, `pos`,
  `script`, `pronunciations`, `tags`).
* Metadata attributes (`dc:contributor`, `dc:source`, `dc:identifier`,
  `note`, `confidenceScore`, `status`) are kept in `meta` as the strings
  written, so `0.80` does not become `0.8`.
* A synset holds its own definitions and examples, each with its
  language, in file order.
* Reading fails on an element or attribute the model has no field for.
  `LexiconExtension` is not handled yet; none of our files uses it.

The database and WN-LMF fill different fields of the same classes: a
database entry has a `wordid` and no `id`, a database synset has no
`ili`, and so on.  Turning one into the other (identifiers, the ILI
map, which senses to release) is what `scripts/getwn.py` does today; it
is not part of the model yet.

## Not done yet

* Applying change records (below) to a base.
* Building the database from the language lexicons.

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
