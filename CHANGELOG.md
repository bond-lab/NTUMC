# Changelog

## Server writes

Every write of a database to `compling.upol.cz:/var/www/ntumc/db/`,
newest first. `scripts/push_dbs.sh` adds an entry here and a line to
`PUSHLOG.tsv` on the server (the server copy also catches pushes made
from other machines). Before each push, the server copies are backed
up to `backup-YYYY-MM-DD/` on the server.

### 2026-11-13 12:33 — eng.db cmn.db jpn.db ind.db eng-jpn.db eng-cmn.db eng-ind.db

- **Pushed:** eng.db cmn.db jpn.db ind.db eng-jpn.db eng-cmn.db eng-ind.db
- **Backup:** `backup-2026-11-13/`
- **Code:** `f4100db` (from bond@tanso)
- **Applied:** Base: server copies of 2026-11-13 (archived in work/ntu-mc/2026-11-13). eng.db: fix_eng_cids.py, catb concept ids renumbered per sentence (767 sentences, 11,663 concepts); fix_cpos.py --mismatched (22,408 offsets). cmn.db: fix_cpos.py --mismatched (411). jpn.db, ind.db: fix_cpos.py --mismatched (779, 62); July 2026 work carried over from the local build: verified retags and BAD comment stamps (14 and 1,032 concepts), propagated stype rows (2,658 and 2,089). eng-jpn/eng-cmn/eng-ind: clink English cids renumbered to match (5,999, 4,799, 4); kc01, kc02 and catb sentence links added (2,238 jpn, 871 cmn; 3 wlinks cmn); 22 stale slinks deleted (check_links.py); eng-ind meta row added

### 2026-10-23 16:45 — eng.db cmn.db

- **Pushed:** eng.db cmn.db
- **Backup:** `backup-2026-10-23/`
- **Code:** `04f90fc` (from bond@tanso)
- **Applied:** restore_triggers.py: eng.db all 14 change-log triggers re-created (lost in the 2026-08-10 push); cmn.db delete_concept_log and delete_cwl_log re-created, delete_word_log repaired (wrote to sent_log, so word deletes failed) (04f90fc). fix_pronoun_tags.py: 25 eng 'either' tokens and 6 cmn 哪 tokens retagged after the pronoun fixes, logged (0916c58). Base: server copies of 2026-08-10, downloaded 2026-10-23.

### 2026-10-23 16:40 — wn-ntumc.db

- **Pushed:** wn-ntumc.db
- **Backup:** `backup-2026-10-23/`
- **Code:** `687e026` plus `d95822e` (from bond@tanso)
- **Applied:** fixlinks.py (no changes); fixwn.py: 33 self-loops, POS-mismatch hypernym fixes, pronoun deixis/of-two/either fixes (ff224b3, 0916c58); apply_cow_cmn.py: Jia Qi Yeo's Chinese edits, 5,911 definitions added, 16 replaced, 314 senses deleted, 125 added (687e026). Base: server copy downloaded 2026-10-23, unchanged since 2026-02-17.

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
