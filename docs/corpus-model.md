# The corpus as Python objects, and as JSON Lines

`ntumc.corpus` holds the NTU-MC corpus as plain dataclasses, reads them
from the SQLite databases, writes and reads them as JSON Lines, and
checks them.  It is the common ground between the three physical forms
of the corpus:

| form | files | reader | writer |
|---|---|---|---|
| SQLite | `build/LANG.db`, `build/FROM-TO.db` | `ntumc.corpus.db` | `ntumc.corpus.dbwrite` |
| XML | one file, `data/ntumc.dtd` | `ntumc.corpus.xmlio` | `ntumc.corpus.xmlio` |
| JSON Lines | one file, one document per line | `ntumc.corpus.jsonl` | `ntumc.corpus.jsonl` |

All three go through the same model, so a corpus can be read from any
one and written to any other, and `scripts/corpus_xml.py` is a thin
front for the XML pair.

The databases are where annotation happens (triggers, logs, annotator
names); XML and JSON are for exchange.  JSON is the easy one to work
with in Python: a document is a single `json.loads`, and the whole
corpus streams one document at a time.

## Reading and playing with a document

```python
from ntumc.corpus import Corpus, jsonl

corpus = Corpus.from_items(jsonl.read("catb.jsonl"))
eng = corpus.document("eng", "catb")
jpn = corpus.document("jpn", "catb")

for sent in eng:
    for concept in sent.tagged():
        words = " ".join(w.word for w in sent.words_of(concept))
        print(sent.sid, concept.clemma, concept.tag, words)

# the Japanese sentences aligned to English sentence 26
for lang, link in corpus.links_from("eng", 26):
    print(lang, corpus.sentence(lang, link.tsid).text)
```

Straight from the databases, without an intermediate file:

```python
from ntumc.corpus import Corpus, db

items = db.read_corpus(
    ["build/eng.db", "build/jpn.db"], ["build/eng-jpn.db"],
    db.Selection(docs={"catb"}),
)
corpus = Corpus.from_items(items)
```

`db.read_documents(path)` yields one `Document` at a time, so a loop
over a whole language needs little memory; `Corpus.from_items` is for
when you want it all in one object.

Making such a file, checking one, converting and loading:

```
.venv/bin/python -m ntumc.corpus dump catb.jsonl \
    --db build/eng.db build/jpn.db --link build/eng-jpn.db --doc catb
.venv/bin/python -m ntumc.corpus validate catb.jsonl
.venv/bin/python -m ntumc.corpus validate --db build/jpn.db
.venv/bin/python -m ntumc.corpus convert catb.jsonl catb.xml
.venv/bin/python -m ntumc.corpus load catb.jsonl --outdir DIR --user NAME
```

The suffix (`.jsonl` or `.xml`) picks the format.  `load` creates or
appends to `DIR/LANG.db` and `DIR/FLANG-TLANG.db`; it keeps the ids
when they are free and refuses otherwise unless `--renumber`, and
`--skip-existing` passes over documents already there while letting
the links refer to them.  The DTD check of an XML file is
`scripts/corpus_xml.py validate`.

## The model

```
Corpus
  info: CorpusInfo            title, license, version
  documents: [Document]
  alignments: [Alignment]

Document    docid, doc, language, title, subtitle, url,
            collection, collection_title, genre
  sentences: [Sentence]
Sentence    sid, text, pid, stype, stype_comment, comment, user
  words:     [Word]      wid, word, lemma, pos, cfrom, cto, comment, user
  concepts:  [Concept]   cid, clemma, tag, wids, ne, candidates,
                         sentiment, sentiment_user, comment, user
  chunks:    [Chunk]     xid, wids, score, comment, user

Alignment   flang, tlang, fdoc
  sents:     [SentLink]     fsid, tsid
  words:     [WordLink]     fsid, fwid, tsid, twid
  concepts:  [ConceptLink]  fsid, fcid, tsid, tcid
             all three also: ltype, conf, comment, user
```

Ids are the database integers: `sid` is unique within a language,
`wid`, `cid` and `xid` within a sentence.  `wids` on a concept or chunk
are the words it covers (the `cwl` and `xwl` tables).  Links give both
ends as ids in the from and to languages of their alignment; an
alignment read from a database or file holds the links of one from-side
document (`fdoc`), so a file can be read a line at a time.

Names follow the database columns, with these differences:

| model | database | XML |
|---|---|---|
| `Sentence.text` | `sent.sent` | `sent` |
| `Word.word` | `word.word` | `surface_form` |
| `.user` | `usrname` / `username` | `last_changed_by` |
| `Concept.tag` | `concept.tag` | `synset_tag` |
| `Concept.candidates` (a list) | `concept.tags` (`; `-separated) | `Tag category="candidates"` |
| `Concept.ne` | `concept.ntag` | `Tag category="ne"` |
| `Concept.sentiment` | `sentiment.score` | `Tag category="sentiment"` |
| `Sentence.stype` | `stype.stype` | `Tag category="stype"` |
| `Chunk.score` | `chunks.score` | `Tag category="sentiment"` |

The `error`/`ewl` tables (empty everywhere) and the `_log` tables are
not part of the model.  An empty string in an optional column reads as
None, so a database, its XML and its JSON compare equal after a round
trip.

Every class is a dataclass with the ids as positional arguments and
the rest as keywords, so `Word(0, "The", lemma="the", pos="DT")`.
`Sentence.word(wid)`, `.concept(cid)`, `.words_of(concept)` and
`.tagged()`, `Document.sentence(sid)`, `.words()` and `.concepts()`,
and `Corpus.document()`, `.sentence()`, `.links_from()` and
`.links_to()` are the lookups.

## The JSON Lines format

One object per line.  `kind` says what it is; the other keys are the
fields above, with `None` and empty lists left out.

```
{"kind":"corpus","title":"NTU-MC","license":"CC BY 4.0"}
{"kind":"document","docid":501,"doc":"catb","language":"eng","title":"The Cathedral and the Bazaar",
 "collection":"essay","genre":"essay","sentences":[
   {"sid":26,"text":"The fact that this bazaar style ...","pid":"p2",
    "words":[{"wid":0,"word":"The","lemma":"the","pos":"DT","cfrom":0,"cto":3}, ...],
    "concepts":[{"cid":0,"clemma":"fact","tag":"06636259-n","wids":[1]}, ...]},
   ...]}
{"kind":"alignment","flang":"eng","tlang":"jpn","fdoc":501,
 "sents":[{"fsid":26,"tsid":27}, ...],
 "concepts":[{"fsid":26,"fcid":0,"tsid":27,"tcid":2,"ltype":"="}, ...]}
```

Documents come before the alignments that refer to them.  The `kind`
line for the corpus is optional.  Reading rejects unknown keys, so a
typo in a hand-made file is caught.

`--slim` (or `jsonl.write(..., slim=True)`) leaves out annotation
history and working data: `user`, `sentiment_user`, `comment`,
`stype_comment` and `candidates`.  Everything a reader of the
annotation needs is still there; what goes is who did it and what the
annotator was offered.

Sizes of whole-language files (2026-10-30), against the viewer's
earlier NDJSON in `display/data/lang/`, which had no offsets, history,
candidates, chunks or links (`make_display.py` now writes the slim
form of this format):

| language | viewer | full | slim | full, gzip | slim, gzip |
|---|---|---|---|---|---|
| eng | 92 MB | 210 MB | 109 MB | 39 MB | 18 MB |
| cmn | 17 MB | 27 MB | 19 MB | | |
| jpn | 11 MB | 15 MB | 12 MB | | |
| ind | 8 MB | 15 MB | 7 MB | | |

In English the candidate lists alone are 78 MB; annotator names are 21
MB and offsets 18 MB.  The links between the four languages add about
4 MB.  Dumping English takes 77 seconds.

## Checking

`validate(items)` works on anything the readers yield, or on a
`Corpus`, and yields `Problem(level, code, where, message)`:

| level | code | meaning |
|---|---|---|
| error | `dup-doc`, `dup-sent`, `dup-wid`, `dup-cid`, `dup-xid` | an id used twice |
| error | `bad-wid` | a concept or chunk covers a word that is not in the sentence |
| error | `offset` | only one of `cfrom`/`cto` set, or outside the text |
| error | `genre` | not one of the six genres |
| error | `link-sent`, `link-word`, `link-concept` | a link end that is not in the corpus |
| warning | `offset` | the text at `cfrom:cto` is not the word |
| warning | `cid-base` | the sentence's concept ids do not start at 0 |
| warning | `no-words` | a concept covering no words |
| warning | `tag`, `candidate` | not a synset id (`12345678-n`, any final letter) or `e`/`w`/`x`; a candidate may also be `unk` |
| warning | `ne` | an unknown named-entity type |
| warning | `wid-order`, `empty-doc` | |

The command line prints them and exits 1 if there were errors.  These
are the checks that the formats themselves cannot express; the DTD
(and, for the databases, the SQL schema) check the shape.  The
database-level repair scripts (`scripts/check_links.py`,
`scripts/fix_cpos.py --mismatched`, `scripts/2026-07/fix_eng_cids.py`)
fix what the link and offset and cid-base checks report.
