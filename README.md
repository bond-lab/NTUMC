# NTUMC

Natural Text Understanding Multilingual Corpus (née Nanyang Technological University Multilingual Corpus and wordnet).

This has been used in:
[Cross Lingual Word Sense Disambiguation with WordNets](https://github.com/jusing-es/clwsd)

### schemas
schemas are in data/*.sql

To create a new database
```
$sqlite3 ces.db < data/ntumc.sql
$sqlite3 ces-eng.db < data/link.sql 
```

### XML

The corpus can be exchanged as XML (DTD: `data/ntumc.dtd`, format
description: [docs/corpus-xml.md](docs/corpus-xml.md), small example:
`data/corpus_example.xml`).  `scripts/corpus_xml.py` dumps the databases
to XML and loads XML back into databases, so new languages or documents
can be prepared as XML and imported:

```
.venv/bin/python scripts/corpus_xml.py dump out.xml --db build/eng.db build/jpn.db --link build/eng-jpn.db
.venv/bin/python scripts/corpus_xml.py load new.xml --outdir DIR
```

