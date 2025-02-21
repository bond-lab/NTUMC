# NTUMC

Natural Text Understanding Multilingual Corpus (née Nanyang Technological University Multilingual Corpus and wordnet).

This has been used in:
[Cross Lingual Word Sense Disambiguation with WordNets](https://github.com/jusing-es/clwsd)

### schemas
schemas are in data/*.sql

load it into a datbase
```
$sqlite3 ces.db < data/ntumc.sql
$sqlite3 ces-eng.db < data/link.sql 
```

