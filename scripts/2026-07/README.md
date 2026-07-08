# One-off scripts — 2026-07 release preparation

Data-repair scripts written for the 2026 corpus release.  Each was (or
will be) run a fixed number of times against the `build/` databases;
they are kept for provenance — together they document every change made
to the corpus data between the Feb-2025 server download and the release.
The permanent, recurring tooling lives one level up in `scripts/`.

Run them from the repository root, e.g.:

```
.venv/bin/python scripts/2026-07/fix_eng_pos.py build/eng.db --dry-run
```

## Corpus repair (part of the "full rebuild" pipeline)

Re-run these, in the order given in `scripts/README.md` ("Full rebuild
from scratch"), whenever the databases are re-downloaded from the server:

| Script | Purpose |
|---|---|
| `migrate_genre.py` | add the `genre` column to all corpus DBs |
| `merge_old_corpora.py` | merge eng/jpn essay + jpn kc from 2013–14 per-genre DBs; import cmn yoursing stype |
| `fix_cmn_sids.py` | swap spec/danc sid ranges in cmn.db; import kumo-no-ito |
| `recover_cmn_concepts.py` | recover concepts dropped from cmn.db, matched against old DBs |
| `merge_ind.py` | restore ind tags demoted between 2016 and 2025 from the 2016 snapshot |
| `fix_jpn_wids.py` | normalise jpn wids/cids to 0-based per sentence |
| `propagate_stype.py` | propagate stype from English via slinks |
| `fix_catb_stype.py` | paragraph stypes for *The Cathedral and the Bazaar* from source HTML |
| `fix_cwl_offbyone.py` | fix concepts linked one sentence off; delete duplicates |
| `fix_eng_pos.py` | the 2017-11-17 POS/tokenisation fixes (Junling), content-verified port; see `fix_eng_pos_targets.json` (expected surfaces baked from the 2017 DBs) and `test_fix_eng_pos.py` |
| `align_kc.py` | create slinks + stypes for kc01/kc02 from article ids in comments |
| `import_links.py` | first import of clinks/wlinks from 2013 link DBs (superseded by `realign_clinks.py`) |
| `realign_clinks.py` | re-derive all clinks from the 2013-10-05 sources against current numbering (fixes issue #6) |

## Comment-suggestion workflow

Annotator comments carry suggestions in a `=synset` / `<synset` /
`~synset` notation.  These are never applied blindly (a review pass
showed ~21% are wrong): the triage classifies them, smaller-model
reviewers judge each in context, and only verified-GOOD ones are
applied.  Rejected ones get a `; BAD[date]: reason` marker appended to
the comment so annotators see the outcome and the triage skips them.

| Script | Purpose |
|---|---|
| `audit_comment_suggestions.py` | classify suggestions vs wordnet + tags -> `docs/comment-suggestions.tsv` (DONE/PARTLY/TODO/MISMATCH/STALE/FREETEXT/REJECTED) |
| `retag_partly.py` | apply verified-GOOD PARTLY rows (needs `docs/partly-verdicts.tsv`) |
| `mark_bad_suggestions.py` | append `BAD[date]` markers for rejected suggestions (concept- or type-level verdicts) |

## Audit / diagnostics (read-only)

| Script | Purpose |
|---|---|
| `audit_annotations.py` | per-document tagged-concept comparison, build vs all historical DBs (`audit.tsv`) |
| `audit_branch.py` | table-level diff of pristine Feb-2025 downloads (`build/*.db.xz`) vs current DBs |
| `audit_content.py` | content-level verification of renumbering-affected rows |

Findings from the audit scripts are written up in
`docs/release-audit-2026-07-05.md`.
