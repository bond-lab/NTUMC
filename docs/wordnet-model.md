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

* Building the database from the language lexicons.
* An editor that writes change records.

## Change records

The master copy of a wordnet is a base release plus an ordered list of
changes.  A release applies the list and its output is the next base.
One record per line, in the order made; the editor appends, nothing is
rewritten.

```
python -m ntumc.wordnet apply BASE.xml CHANGES.jsonl NEW.xml --version 2.2
```

```json
{"id": "2026-11-13T10:02:11Z-fcbond-1", "action": "remove_sense",
 "lexicon": "wnja", "synset": "wnja-02084071-n", "lemma": "イヌ",
 "user": "fcbond", "source": "native check", "reason": "not used for this meaning",
 "base": "wnja-2.1"}
```

Every record has `id`, `action`, `lexicon`, `user`, `source` and
`reason`; `base` is the release it was made against and `date` the day
it was decided, where the id does not say.

| action | needs | does |
|---|---|---|
| `add_sense` | `synset`, `lemma` | adds the word to the synset (`new`: confidence); makes the entry if there is none |
| `remove_sense` | `synset`, `lemma` | removes it; an entry left with no sense goes too |
| `keep_sense` | `synset`, `lemma` | nothing: records a decision to keep a sense |
| `set_confidence` | `synset`, `lemma`, `new` | sets `confidenceScore` |
| `rename_lemma` | `synset`, `lemma`, `new` | gives the sense another written form |
| `set_count` | `synset`, `lemma`, `new`, `corpus` | how often the sense was seen in a corpus; 0 removes the count |
| `set_frames` | `synset`, `lemma`, `new` | sets the frames the sense names (`subcat`), as frame ids with spaces between; an empty `new` removes them |
| `set_note` | `synset`, `lemma`, `new` | sets the note on the sense (`old`: the note expected before); an empty `new` removes it |
| `add_form` | `lemma`, `pos`, `new` | adds a written form (`script`) |
| `remove_form` | `lemma`, `pos`, `old` | removes a written form |
| `set_tag` | `lemma`, `pos`, `category`, `new` | sets the lemma's tag in a category (e.g. `adjective-class`); an empty `new` removes it |
| `set_pronunciation` | `lemma`, `pos`, `new` | sets the lemma's one pronunciation (`notation`: how it is written or was made, e.g. `composed`); an empty `new` removes it |
| `set_definition` | `synset`, `new` | replaces the definition `old`, or adds one (`lang`) |
| `add_example` | `synset`, `new` | adds an example (`lang`) |
| `add_relation`, `remove_relation` | `synset`, `link`, `target` | one direction; the reverse is its own record |
| `add_sense_relation`, `remove_sense_relation` | `synset`, `lemma`, `link`, `target`, `target_lemma` | a relation between two senses, each named by synset and word (`subtype`: its `dc:type`) |
| `reject_sense_relation` | `synset`, `lemma`, `target`, `target_lemma` | nothing: records a decision that the two senses are not related (with `link`: not by that relation, in that direction); adding the relation later is a conflict |
| `add_synset` | `synset`, `pos`, `new` | a new synset with definition `new`, or none if `new` is empty (`ili`, `identifier` for a local concept id) |
| `remove_synset` | `synset` | drops a synset no word is in, and the relations pointing to it |
| `set_identifier` | `synset`, `new` | sets the synset's `dc:identifier`, which names its concept across lexicons (`ntumc00392`, `pronoun:Plc;Int;Loc`); an empty `new` removes it |
| `set_ili` | `synset`, `new` | sets the synset's ILI (`old`: the ILI expected before); an empty `new` removes it; a conflict if another synset of the lexicon has that ILI |
| `set_pos` | `synset`, `new` | sets the synset's part of speech (`old`: the one expected before); its senses go to entries of that part of speech, made if there are none |
| `merge_synset` | `synset`, `target` | moves senses and relations to `target` and drops `synset` |

Where a lemma has several entries (homographs), `pos`, `reading` (one
of the entry's forms) or `entry` (its id) says which; `sense` (a sense id) names one sense
where an entry has two in a synset.  New entries and
senses get ids made like the lexicon's others.  More actions can be
added as needed.

After writing, each `release.py` runs the validation of the `wn`
module on the files (`ntumc.wordnet.validate`).  An error stops the
release, and so do three warnings: an ILI on two synsets (`W302`), a
word twice in a synset (`W202`) and two entries for one word in a
synset (`W203`).  The other warnings are counted in the log.  wnja
lets `W203` pass: its entries are one for each reading, and a word
with two readings has both in a synset.

A change that does not fit the base is a conflict: its sense is not
there, its `old` value is not the current one, what it adds already
exists, or the record is incomplete.  `apply` lists the conflicts and
writes nothing until a person has settled them.  `source` is required,
and a model alone (a source beginning `model`) is not a source for an
addition, which includes setting a tag or a pronunciation.  A rejection does not need its
senses to be in the lexicon: often one of them was the mistake.

A lexicon that extends another (COW and Wordnet Bahasa extend omw-en)
does not keep a synset that says nothing: after the changes, their
release step calls `drop_empty_synsets`, which drops every synset with
no sense, no definition, no ILI definition, no example and no local
concept id, unless it is marked `lexicalized="false"`.  The base wordnet
still has the concept through the ILI.

### Checked against wnja

wnja's `corrections/` files (12 definitions, 2,750 sense rows other
than `add`, 1 form) were turned into 2,763 change records and applied
to the wnja build as it is before `tweak_wnja.py`.  There were no
conflicts, and every entry, form, sense and confidence came out the
same as from wnja's own code.  The only difference is 14 definitions
containing a full-width space, which wnja's XML library turns into an
ordinary space and this code keeps.

## Local concept ids

Concepts we share across languages before CILI has them get a local
identifier, `ntumc00001`.  The registry is its own repository,
`omw-ntumc` (`registry.tsv`, checked by `check_registry.py`):

```
local_id  ntumc_synset  pos  name  definition  proposed_by  date  cili  status
```

* `local_id` is `ntumc` and five digits; it never changes and is never
  reused.  The prefix keeps our ids apart from other projects' when
  several shared lexicons are merged.
* The definition is in English and meets the CILI rule (at least 20
  characters or five words).
* `status` is `draft`, `proposed`, `submitted`, `granted` or `withdrawn`.
* In WN-LMF a synset for a local concept has `ili="in"`, an
  `ILIDefinition`, and `dc:identifier="ntumc00001"`.  The local id never
  goes in the `ili` attribute, which must hold a CILI id, `in` or
  nothing.  Cygnet already merges synsets across lexicons on
  `dc:identifier`.
* When CILI grants an id, it is entered in `cili`, and builds write that
  id in `ili` from then on, keeping the `dc:identifier`.
* The concepts themselves (English definition, relations) live in one
  shared lexicon, `omw-ntumc`, with `language="mul"`, as omw-pronoun
  does; the language lexicons only add words.

## The minimal lexicon and the export

Each language wordnet is released as two lexicons.

| lexicon | id | what it is |
|---|---|---|
| minimal | `cow-min` | the master: what the wordnet itself says |
| export | `cow` | built from the minimal one and `omw-ntumc`, for users who want one file |

In the minimal lexicon a concept that has an ILI is an ordinary synset.
A concept CILI does not have yet is a synset with the concept's
`dc:identifier`, the words, and whatever only this wordnet says about it
(a definition in its own language, a relation the shared lexicon lacks).
It names the shared lexicon in a `Requires`.

`ntumc.wordnet.shared` makes one from the other:

* `minimal(lexicon, shared)` takes out the shared lexicon's definitions
  and relations and renames the lexicon `ID-min`.
* `export(minimal, shared)` puts them back and renames it `ID`.  A
  relation is added when the lexicon has its target; a definition, when
  the synset has none of its own.

`minimal` removes exactly what `export` restores, so the export says
everything the lexicon said before it was split.  It can say more: on
COW 1.2 it gains 222 relations to or from synsets the change log added, and
one definition.  `write_release(lexicon, shared, out)` writes both files
and fails if the export lacks anything; `load(path, sha256)` reads the
shared lexicon a release is pinned to.

When CILI grants a concept an id, the synset gets the `ili` and is from
then on an ordinary synset of the minimal lexicon.

## From an existing build to a change log

```
python -m ntumc.wordnet diff OLD.xml NEW.xml CHANGES.jsonl \
    --user fcbond --source "wnja build" --reason "since 2.1" --base wnja-2.1
```

`diff` compares two versions by what they say (which word is in which
synset and how surely, forms, definitions, examples, relations), not by
identifiers or order, and writes the change records that turn the old
into the new.  It then applies them to the old version and reports
anything still different: entry and sense metadata have no change
record.  This is how a wordnet moves to base plus log: run the old
build one last time and diff it against the last release.

Checked on wnja: the released 2.1 against a build of the repository
today gives 2,133 records (34 senses removed, 12 added, 3 confidences,
6 forms, 3 definitions, 2 corpus counts, 2,073 sense relations: the
agentive links).  They apply with no conflict and leave nothing
unexplained.
