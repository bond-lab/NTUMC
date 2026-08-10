# NTU-MC Release Audit — 2026-07-05

Complete audit of the `display-corpus` branch's release preparation,
verifying that no information was lost while copying corpus versions and
applying fixes.  Method: the pristine Feb-2025 server downloads survive as
`build/*.db.xz`; each was decompressed and compared row-by-row (and, where
keys were renumbered, content-by-content) against the current fixed
`build/*.db` files.  Historical claims were cross-checked against the
snapshots in `/home/bond/work/ntu-mc/`.

Verification scripts: `audit_branch.py`, `audit_content.py` (session
scratchpad); outputs `audit_branch.out`, `audit_content.out`.

## Verdict

**No unaccounted information loss from branch work.**  Every difference
between the pristine downloads and the current build databases traces to a
documented, deliberate fix.  The branch *recovered* substantial data
(eng +769 essay sentences, jpn +2,793 essay/kc sentences, ind +3,941
recovered tags, cmn +1,191 recovered tags, 17k+ cross-lingual clinks,
~11k new stype rows).  Three caveats are flagged below; the log-table
caveat **must** be handled before pushing to the server.

## Per-language accounting (pristine Feb 2025 → current)

| DB | Change | Explanation (commit/script) |
|---|---|---|
| eng | +769 sents, +11,651 concepts | essay (catb) merge — `merge_old_corpora.py` (3971a66) |
| eng | −13 concept keys | 3 retagged; 9 deleted as off-by-one duplicates (`fix_cwl_offbyone.py`); 1 exact duplicate (`video tape` ×2 → ×1) |
| eng | −68 cwl rows | 25 orphans (no concept) + off-by-one remaps (c5eef3c, d42313a) |
| eng | word content | **0 lost** (multiset by sid+surface) |
| jpn | +2,793 sents | essay 773 + kc 2,020 merge — exact match (3971a66) |
| jpn | word keys churn | 0-based wid renumbering (728e051); **0 words lost by content** |
| jpn | −4 concepts | 3× 話す + 御釈迦様, deleted as off-by-one duplicates (each had a same-clemma/same-tag neighbour) |
| cmn | 14 sids removed, 79 added | spec/danc sid swap (`fix_cmn_sids.py`); all 14 sentence texts confirmed present under new sids; net +65 = kumo-no-ito import |
| cmn | −1 sent (`fields.`) | documented bogus sentence deletion (f48fcf8, docs/bogus-sentences.md) |
| cmn | −6 酿豆腐 concepts | off-by-one duplicate deletion (`fix_cwl_offbyone.py`) |
| cmn | +1,191 tagged concepts | `recover_cmn_concepts.py` |
| ind | 75 clemma changes, +3,941 synset tags | `merge_ind.py` re-import from 2016 (e.g. `katanya`→`kata` + tag where build had NULL) |
| ind | −638 cwl keys | 636 confirmed orphans in pristine; 2 tied to the one deleted duplicate concept (`carrot cake`) |
| ces | −2 concepts | duplicate `být` (twin at same sid) + `šupina`, off-by-one duplicates |
| ces | ~44 tag renames | `-z` synsets renamed to correct POS (bbb0f20), e.g. `80002491-z`→`-a` |
| ita, zsm, yue | no data changes | only stype additions / word_log rebuild |
| all corpus DBs | +stype rows | `propagate_stype.py`, `align_kc.py`, alvas/stype.tab import |
| wn-ntumc | −111 synsets (net) | empty-synset filtering + `-z`/POS renames; all 19 affected senses confirmed moved to the renamed synsets, except one (below) |
| wn-ntumc | −200 synlinks (net) | 375 duplicate rows removed, 33 self-loops (W403/W502 fixes) |
| wn-multix | unchanged | — |

## Caveats

### 0. Update (same day): scripts/README.md context

`scripts/README.md` documents `droplogs.sh` as *intended* for the build/
release copies ("does not touch the server originals"), so the log-table
drop below is expected behaviour for local copies, not an accident.  The
upload consequence still stands: these local copies must never be pushed
back over the server originals.  `fix_corpus.py --download/--push` is the
existing server-sync mechanism (`--push` has no server-side backup step —
add one before using it).  Note also that several fix scripts
(`fix_cwl_offbyone.py`, `fix_corpus.py`) drop the log triggers to work;
eng.db now has 3 of its original 14 triggers, jpn.db none.  Re-applying
fixes to fresh server downloads (which carry the full trigger set and
logs) makes this moot, provided the scripts restore triggers afterwards.

### 1. Log tables were dropped from the build copies (CRITICAL for upload)

`eng.db`, `jpn.db`, `ita.db`, `ces.db`, `yue.db`, and `wn-ntumc.db` in
`build/` lost their `*_log` history tables (pristine eng.db had 1.19M
`word_log` rows and 8 further log tables; the current file has only the
190k `word_log` rows re-created by branch fix scripts).  `cmn.db` and
`ind.db` kept theirs.  Nothing is unrecoverable — the pristine `.xz`
archives and the server retain full history — but **the current build DBs
must not be pushed to the server as-is**, or the server's annotation
history would be destroyed.  The upload plan must re-download the server
DBs (with logs), re-apply the fixes on top, and only then push back.

### 2. `fix_cwl_offbyone.py` deleted ~22 tagged concepts across languages

All were the documented "duplicate" action (concept misaligned by one
sentence whose correct sentence already had the same annotation).  They
are individually listed in `audit_content.out` and recoverable from the
`.xz` archives if any deletion is judged wrong.

### 3. One wordnet sense lost outright

`late-night` (wordid 612687) lost its only sense when custom synset
`90000428-n` was deleted; the word now has no synsets.  Worth a manual
check.  (The similar `90000405-n` case is fine — `jam` retains 4 standard
senses.)

## Historical (server-side) differences — not branch losses

The old-snapshot comparison (`audit.tsv`) flagged 174 cmn docs as FEWER
and 5 as MISSING.  Investigated:

- `cmn-catb` "MISSING" — name-matching artifact; the essay corpus is in
  cmn.db as doc `catb` with **more** tagged concepts (12,458) than the
  2013 snapshot (12,399).
- `dm` "MISSING" — `dm` is *The Dancing Men* = story doc `danc`, present
  in eng.db and cmn.db.  Name artifact.
- cmn yoursing FEWER: of 43,915 "tagged" concepts in the 2013 snapshot,
  9,125 have no counterpart in build — but 54% carried placeholder tags
  (`u`/`m`/`s`/`p`), and 96% (8,762) were already absent from the
  2016-11-30 server snapshot.  This was 2013→2016 annotator QC on the
  server, predating this branch by a decade.  Only 363 concepts
  disappeared server-side between 2016 and the Feb 2025 download.
- eng `danc`: 280 fewer tagged than 2013 but 1,394 more total concepts —
  same pattern of server-side retagging (tags demoted to `x`/`w`/`e`),
  as previously established for ind (docs/data-audit-2026-06-18.md §3).

## Cross-lingual link databases

**Update 2026-07-08 (issue #6):** the clinks that `import_links.py`
created referenced pre-merge concept ids (4,166 + 473 orphaned endpoints
in eng-cmn, 4,480 in eng-jpn; the eng-ind rows were largely mispaired
via an unverified sid-formula fallback).  All clink tables were rebuilt
by `scripts/2026-07/realign_clinks.py`, which re-derives every link from
the 2013-10-05 sources against the current databases (text-matched
sentences, clemma/tag/position-matched concepts, slink-validated pairs).
Result: eng-cmn 12,466, eng-jpn 11,673, eng-ind 16,149 clinks, zero
orphaned endpoints.  usrname is NULL, matching the 2013 sources (their
link tables carry no usrname column, so batch-imported links display
blank in IMI while real annotator edits keep their names).  Unresolved
source links are mostly concepts deleted server-side 2013→2016.

`build/` link DBs strictly gained: eng-cmn 7,426 slinks (2016: 6,555),
eng-jpn 3,773 (1,535), eng-ita 475 (0), eng-ind/eng-zsm unchanged, plus
17,225 imported clinks (e4890fc) and new kc slinks (`align_kc.py`).
`eng-ces.db`/`ces-eng.db` use a different schema (no clink table).
Note: link DBs are not covered by `release.sh` download/upload lists.
