# Changelog

## Server writes

Every write of a database to `compling.upol.cz:/var/www/ntumc/db/`,
newest first. `scripts/push_dbs.sh` adds an entry here and a line to
`PUSHLOG.tsv` on the server (the server copy also catches pushes made
from other machines). Before each push, the server copies are backed
up to `backup-YYYY-MM-DD/` on the server.

### 2026-08-10 — corpus databases and link databases

Reconstructed afterwards from the server backup directory and the git
history; no log was kept at the time.

- **Pushed:** `eng.db`, `cmn.db`, `jpn.db`, `ind.db`, `ita.db`,
  `ces.db`, `yue.db`, `zsm.db` (15:01); `eng-cmn.db`, `eng-jpn.db`,
  `eng-ind.db` (15:38). `wn-ntumc.db` was not pushed (server copy last
  changed 2026-02-17).
- **Backup:** `backup-2026-08-10/`
- **Code:** around `4d3c917`–`88fa9e7` (2026-08-10)
- **Applied (inferred):** the corpus repair pipeline in
  `scripts/README.md` ("Full rebuild from scratch"). Verified only that
  the server databases have the genre column and keep their `*_log`
  tables.
