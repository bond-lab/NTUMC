# NTU-MC corpus XML format

The NTU Multilingual Corpus is stored and annotated in SQLite (one
database per language plus one per language pair, see `data/ntumc.sql`
and `data/link.sql`).  For exchange there is an XML format, defined by
the DTD `data/ntumc.dtd`, that holds the same information: one file can
carry any number of languages and the links between them.

`scripts/corpus_xml.py` converts in both directions:

```
# database -> XML (one file, several languages, links from the pair databases)
.venv/bin/python scripts/corpus_xml.py dump out/ntumc.xml \
    --db build/eng.db build/jpn.db --link build/eng-jpn.db

# only some documents or sub-corpora
.venv/bin/python scripts/corpus_xml.py dump out/catb.xml \
    --db build/eng.db build/jpn.db --link build/eng-jpn.db --doc catb
.venv/bin/python scripts/corpus_xml.py dump out/stories.xml \
    --db build/eng.db build/ces.db --collection story

# XML -> database: creates (or appends to) DIR/LANG.db and DIR/FLANG-TLANG.db
.venv/bin/python scripts/corpus_xml.py load new-language.xml --outdir DIR

# check a file against the DTD (needs xmllint, package libxml2-utils)
.venv/bin/python scripts/corpus_xml.py validate new-language.xml
```

`load` validates first and refuses an invalid file (`--no-validate`
skips this).  A complete small example is `data/corpus_example.xml`:
English, Italian and Spanish with sentence, word and concept links.

The DTD was first drafted by Giulia Bonansinga and Luís Morgado da Costa
in 2019 (github.com/lmorgadodacosta/NTUMC) for the cross-lingual WSD
work in github.com/jusing-es/clwsd; this version adds optional
attributes so that a database round-trips without loss.

## Structure

```
Corpus (Document+, Alignment?)
  Document (Sentence+)
    Sentence (Word*, Concept*, Chunk*, Tag*)
      Word (Tag*)
      Concept (Tag*)
      Chunk (Tag*)
  Alignment (DocAlignment*, SentAlignment*, WordAlignment*, ConceptAlignment*)
```

Everything is in attributes; elements have no text content.  The order
of children is fixed by the DTD: all words, then concepts, then chunks,
then tags; in the alignment block all sentence links, then word links,
then concept links.

### Corpus

| attribute | | database |
|---|---|---|
| `corpusID` | required | id of the file; also the default `collection` |
| `title` | required | `meta.title` |
| `linguality` | required | `multilingual` or `monolingual` |
| `license` | | `meta.license` |
| `version` | | `meta.version` |

### Document

| attribute | | database |
|---|---|---|
| `docID` | required, unique | `doc.docid` |
| `doc` | required | `doc.doc`, the short machine name (e.g. `catb`, `kc01`) |
| `language` | required | ISO 639-3 code: `eng`, `jpn`, `cmn`, `ind`, `ita`, `ces`, `yue`, `zsm` ... Decides which `LANG.db` the document goes to |
| `title` | required | `doc.title` |
| `subtitle`, `url` | | `doc.subtitle`, `doc.url` |
| `collection` | | `corpus.corpus`, the sub-corpus short name (`story`, `kc`, `yoursing`, `essay`, `gloss`) |
| `collection_title` | | `corpus.title` |
| `genre` | | `corpus.genre`: `essay`, `fiction`, `lexical`, `news`, `online` or `tourism`. Needed when the collection is new to the database |

### Sentence

| attribute | | database |
|---|---|---|
| `sid` | required, unique | `sent.sid` |
| `sent` | required | `sent.sent`, the raw text |
| `pid` | | `sent.pid`, paragraph id |
| `comment`, `last_changed_by` | | `sent.comment`, `sent.usrname` |

A `<Tag category="stype" value="p"/>` child records the sentence's
structural type (`stype` table): `p` paragraph start, `h0`-`h7` heading
levels, `item`, `author`, `translator`.

### Word

| attribute | | database |
|---|---|---|
| `wid` | required, unique | `word.wid` (position in the sentence, from 0) |
| `surface_form` | required | `word.word` |
| `lemma` | | `word.lemma` |
| `pos` | | `word.pos`, the language's own tagset |
| `upos` | | universal POS; stored in `word.pos` only if `pos` is absent |
| `cfrom`, `cto` | | character offsets into `sent`, end exclusive |
| `comment`, `last_changed_by` | | `word.comment`, `word.usrname` |

### Concept

A concept is a sense annotation over one or more words.

| attribute | | database |
|---|---|---|
| `cid` | required, unique | `concept.cid` |
| `wid` | | the words it covers, space separated (`cwl` table). Should always be there; a few orphan concepts in the databases have none |
| `clemma` | required | `concept.clemma`, the lemma as tagged (may be a multiword expression) |
| `synset_tag` | | `concept.tag`: a synset id such as `02084071-n`, or `e` (tokenisation error), `w` (wordnet gap), `x` (not in wordnet). Absent if untagged |
| `comment`, `last_changed_by` | | `concept.comment`, `concept.usrname` |

Tag children:

| category | value | database |
|---|---|---|
| `sentiment` | -100 .. 100 | `sentiment.score` (`last_changed_by` is `sentiment.username`) |
| `ne` | `per`, `org`, `loc`, `dat`, `num`, `oth`, `nam` | `concept.ntag`, named-entity type |
| `candidates` | `; `-separated synset ids | `concept.tags`, the senses the annotator chose from |

### Chunk

A chunk groups words (`chunks` and `xwl` tables); so far it is used for
sentiment over phrases.

| attribute | | database |
|---|---|---|
| `chid` | required, unique | `chunks.xid` |
| `wid` | | the words it covers, space separated |
| `comment`, `last_changed_by` | | `chunks.comment`, `chunks.username` |

A `<Tag category="sentiment" value="60"/>` child is `chunks.score`.

### Alignment

The link databases (`eng-jpn.db` and so on) become one block at the end
of the file.  Each element links one source id to one or more target
ids; the languages come from the documents the ids belong to, so a
single file can hold every language pair.

| element | attributes | database |
|---|---|---|
| `SentAlignment` | `sid_from`, `sid_to` | `slink` |
| `WordAlignment` | `wid_from`, `wid_to` | `wlink` |
| `ConceptAlignment` | `cid_from`, `cid_to` | `clink` |
| `DocAlignment` | `docID` (the aligned documents) | not stored |

All three take `type` (`manual`, the default, or `automatic`), `ltype`,
`conf` (0.0 - 1.0), `comment` and `last_changed_by`.  `ltype` is the
link type as stored in the database; for concept links it is the
wordnet relation between the two concepts: `=` same synset, `<`
hyponym, `>` hypernym, `~` related, `!` antonym.  `type="automatic"`
with no `ltype` is stored as `ltype = 'automatic'`.

## Ids

Every `docID`, `sid`, `wid`, `cid` and `chid` is an XML ID: unique in
the whole file, starting with a letter or underscore.  `dump` writes
them as

```
eng-d502            document 502 of eng.db
eng-s10000          sentence 10000
eng-s10000w3        word 3 of that sentence
eng-s10000c1        concept 1
eng-s10000x0        chunk 0
```

`load` keeps the numbers when ids have this shape (the language prefix
is optional) and the numbers are free in the target database, and
otherwise assigns the next free number; with `--renumber` it always
assigns fresh document and sentence numbers.  Word, concept and chunk
numbers count from 0 within the sentence when the ids do not supply
them.  Loading a file whose sentence numbers are already taken is an
error, so that a second load of the same data cannot silently overwrite
an existing one.

## Adding a new language

To add, say, French sense annotations aligned to the English corpus:

1. Dump the English documents you are aligning to, to get their ids:
   `corpus_xml.py dump eng.xml --db build/eng.db --doc catb`.
2. Write the French documents in the same format, with `language="fra"`,
   a `collection` and a `genre`, and ids such as `fra-s1`, `fra-s1w0`.
   Only `surface_form` is required for a word; add `lemma`, `pos`,
   `cfrom` and `cto` when you have them.  Tag senses as concepts with
   `synset_tag` set to the synset id.
3. Put the links in an `<Alignment>` block, referring to the English
   ids from step 1 (`sid_from="fra-s1" sid_to="eng-s1"`).  The English
   documents must be in the same file for the ids to resolve, so
   concatenate the two document sets under one `<Corpus>`.
4. Validate, then load into a directory holding a copy of `eng.db`:
   `corpus_xml.py load fra.xml --outdir DIR --skip-existing`.  You get
   `DIR/fra.db` and `DIR/fra-eng.db`; the English documents, already in
   `eng.db`, are passed over but the links to them are kept.

   Loading into an empty directory instead gives a self-contained set:
   the English documents in the file are created there too.

## What is not covered

* Error annotations (`error`, `ewl` tables): unused in the current
  databases.
* The `*_log` tables (annotation history): `load` writes new log rows
  through the database triggers, but the old history is not carried.
* Empty strings become NULL on the way through, and a non-numeric
  `cfrom` or `cto` (one Japanese row has text there) is dropped with a
  warning.
* `meta.master` and the per-pair `meta.comment`.
