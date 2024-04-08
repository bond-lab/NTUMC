# NTUMC
Nanyang Technological University Multilingual Corpus

### get current schema
sqlite3 /var/www/ntumc/db/2020-HG2002-phase1/eng.db .schema > ntumc.sql


### load it into a datbase
sqlite3 wilde.db < data/ntumc.sql
