# Senses the review removed that the corpus is tagged with

A sense review removed these senses from COW (`cmn.tsv`, 408) and
Wordnet Bahasa Indonesian (`ind.tsv`, 230), but the NTU-MC corpus has
concepts tagged with them: a tagger and the review disagree.  One row
per sense, most used first, made on 2026-11-13 from the corpus
databases and the wordnet database frozen that day.

| column | content |
|---|---|
| `ruling` | to fill in: `RESTORE` (the sense is right: put it back), `REMOVED` (the review is right: the corpus tags need retagging), or a note |
| `uses` | how many corpus concepts have this tag and lemma |
| `synset`, `lemma`, `english` | the sense: synset id, the lemma as tagged, the English name and definition |
| `review_reason`, `review_source` | why the review removed it, and which review |
| `example_1`, `example_2` | the first two corpus sentences tagged with it |
