# Audit: /home/bond/work/ntu-mc/

Audited 2026-06-20.  This directory contains the original per-genre
databases and fix scripts from 2013--2024, before corpora were merged
into the live per-language databases on compling.upol.cz.

## Summary of Findings

### Data confirmed MISSING from live databases

| Data | Source in work/ | Live status | Action |
|------|----------------|-------------|--------|
| **eng essay (catb)** | `round0/eng-catb.db` (769 sent, 11285 concepts, sid 101--869) | Not in eng.db at all | Merge into eng.db as corpusID=4 (essay) |
| **jpn essay (catb)** | `round0/jpn-catb.db` (773 sent, 11031 concepts, sid 1--773) | jpn.db has corpus row but no docs/sents | Merge into jpn.db |
| **jpn kc (news)** | `round0/jpn-kc.db` (2020 sent, 29586 concepts, sid 100000--102019) | jpn.db has corpus row but no docs/sents | Merge into jpn.db; renumber sids to 60000+ |
| **cmn stype** | `alvas/stype.tab` (3280 entries, H/P for yoursing) | cmn.db has 0 stype entries | Import; also need stype for essay/kc/story |
| **eng stype (yoursing, kc)** | partially in `2024-08-30/fix-stype.py` | eng.db: story has 35% stype; kc/yoursing have 0% | Apply fix-stype from sh-canon for story; need new work for yoursing/kc |
| **cross-lingual links** | `2013-10-05/eng-{cmn,jpn}-{essay,story,dm}-links.db` | live eng-cmn.db has 498KB; these may have additional links | Compare and merge |

### Data already in live databases (confirmed)

| Data | Source in work/ | Live status |
|------|----------------|-------------|
| eng kc (news) | `round0/eng-kc.db` (2138 sent, old sid 100000+) | eng.db has same data renumbered to sid 60000--62137 |
| eng story (spec, danc) | `round0/eng-story.db` (1198 sent) | eng.db has 47227 story sents (many more added since) |
| cmn essay (catb) | `round0/cmn-catb.db` (816 sent, sid 0--815) | cmn.db has it as corpusID=1, sid 1--816 |
| cmn story (spec, danc) | `round0/cmn-story.db` (620 sent) | cmn.db corpusID=3, 1226 sents |
| cmn kc (kc01, kc02) | `round0/cmn-kc.db` (2138 sent) | cmn.db corpusID=2, sid 60000--62137 |
| cmn yoursing | multiple snapshots | cmn.db corpusID=4, 3280 sents |
| ind yoursing | `ind-yoursing.db` (2197 sent, old format) | ind.db has 3098 sents (expanded since) |
| jpn story (spec, danc) | `round0/jpn-story.db` (702 sent) | jpn.db corpusID=3, 1463 sents (kumo-no-ito added) |

---

## Directory-by-Directory Details

### `round0/` -- Original per-genre databases (pre-merge, ~2013)

The oldest snapshot.  Per-genre DBs use the OLD schema: `subcorp` table
instead of `corpus`/`doc`; `concept` has `(sid, wid, cid, ...)` instead
of separate `cwl` table; no `stype` table.

Key databases:
- `eng-catb.db` -- **English essay, 769 sents, sid 101--869.  NOT IN LIVE DB.**
- `jpn-catb.db` -- **Japanese essay, 773 sents, sid 1--773.  NOT IN LIVE DB.**
- `jpn-kc.db` -- **Japanese news, 2020 sents, sid 100000--102019.  NOT IN LIVE DB.**
  Needs renumbering to sid 60000+ to match the convention.
- `eng-kc.db` -- English news, same data as live (renumbered to 60000+)
- `cmn-catb.db` -- Chinese essay, already in live cmn.db
- Cross-lingual link DBs: `eng-cmn-sb-links.db`, `eng-jpn-sb-links.db`

### `round1/` -- Second round with renumbered sids (~2013)

Updated copies with some sids renumbered (cmn-kc now at 60000+).
Also has cross-lingual link databases:
- `eng-cmn-essay-links.db` (slink=871, clink=4849)
- `eng-cmn-story-links.db` (slink=1352, clink=7906)
- `eng-jpn-essay-links.db` (slink=772, clink=6463)
- `eng-jpn-story-links.db` (slink=1462, clink=5809)
- `eng-ind-yoursing-links.db` (slink=227KB -- partial)

### `rounda/` -- Copy of round0 with some fixes

Appears to be a working copy of round0 with minor fixes applied.
Same data as round0 for most files.

### `2013-09-03/` -- Snapshot with prefix/ subfolder

Contains per-genre DBs plus a `prefix/` copy (pre-renumbering) and
`wnall.db` (165MB wordnet).  The `eng-essay.db` here is the essay
corpus in the new subcorp format (sid 101--869, 12733 concepts).
Also has jpn-essay (sid 1--773) and jpn-kc (sid 100000+).

### `2013-10-05/` -- Most complete early snapshot

Same as 2013-09-03 but with updated cross-lingual links.
**Best source for the cross-lingual link databases:**
- `eng-cmn-dm-links.db` (slink=680, wlink=3136, clink=2857)
- `eng-cmn-essay-links.db` (slink=871, clink=4849)
- `eng-cmn-story-links.db` (slink=1352, clink=7906)
- `eng-jpn-dm-links.db` (slink=758, wlink=2112, clink=2745)
- `eng-jpn-essay-links.db` (slink=772, clink=6463)
- `eng-jpn-story-links.db` (slink=1462, clink=5809)
- `eng-ind-yoursing-links.db` (slink=1831, clink=23585)

### `2013-12-14/` -- Japanese fix scripts

Contains `fix-jpn.py` for Japanese verbal-noun light-verb POS fixes
and a `cmn-yoursing.db` snapshot.

### `2014-04-04/` -- Latest per-genre snapshot

Most recent per-genre DBs before the project switched to merged format.
- `eng-essay.db` (769 sent, 12733 concepts) -- same essay data
- `eng-story.db`, `eng-story-gold.db` (gold standard copy)
- `jpn-essay.db` (773 sent, 10937 concepts)
- `jpn-story.db` (702 sent)
- cmn and ind yoursing snapshots

### `2015-09-30/ntumc/` -- First merged per-language databases

The first snapshot where per-genre DBs were merged into per-language DBs
(eng.db, cmn.db, jpn.db, etc.) with the new `corpus`/`doc` schema.
**Essay data was already missing at this point** -- the merge never
included the essay corpus for eng or jpn.

Also contains annotator-split DBs (engA-D, cmnA-D, etc.) and
cross-lingual link DBs in the new format.

### `2016-11-30/` -- Snapshot with learner annotator data

Full server snapshot.  Contains learner annotator DBs
(`2016-eng.learner-annotator[1-6].db`) and Korean/Myanmar data.
Essay still missing from eng.db.

### `2017-11-17/` -- Punctuation fixes

English DB with punctuation consistency fixes (`fixpunct.py`,
`fixclem.py`).  Contains `hg2051/` subdirectory with a cleaned
version.  No essay data.

### `2018-09-18/` -- English snapshot

`eng.db` (493MB) and `eng-cp.db` (copy).  `phase2/engA.db` annotator
DB.  No essay.  No stype.

### `2024-08-30/` -- Most recent fix session

Downloaded eng.db from server, applied:
1. `fix-sent-11224.py` -- added missing words for sentence 11224 (danc)
2. `fix-stype.py` -- populated stype from sh-canon headers/paragraphs
   for story corpus (h1, p) and kumo-no-ito (manual entries).
   **This is where the current 16412 story stype entries came from.**
   The push back to server was commented out but apparently done.

### `jpn/` -- NTT-AT annotation data

Contains databases in the NTT-AT format (`corpus_sent`, `corpus_word`,
`corpus_lid` tables):
- `at-jpn-catb.db` -- Japanese essay (catb), 773 sents, NTT-AT format
- `at-jpn-kc01.db` -- Japanese news kc01, 1000 sents, NTT-AT format
- `tk-jpn-kc02.db` -- Japanese news kc02, 1020 sents
- `jpn-sb.db` -- Japanese Speckled Band, 702 sents

These are the **source annotation from NTT-AT collaborators** for
Japanese essay and news data.  The data was converted into the round0
per-genre format but apparently never merged into the live jpn.db.

### `alvas/` -- Chinese yoursing stype data

Liling Tan's work on Chinese yoursing annotation:
- `stype.tab` -- **3280 stype entries** (H=heading, P=paragraph) for cmn yoursing
  sid 100001--103279.  **Not in live cmn.db.**
- `subcorp2.tab` -- subcorpus metadata for cmn yoursing (335 entries with URLs)
- `sent.tab`, `word.tab`, `concept.tab` -- cmn yoursing data in tab format
- `cmn-yoursing.db` -- older cmn yoursing snapshot

### `data/` -- Cross-lingual alignment TSV files

- `eng-cmn-align-catb.tsv` -- English-Chinese essay alignment
- `eng-cmn-align.tsv` -- English-Chinese alignment (story?)
- `eng-jpn-align-catb.tsv` -- English-Japanese essay alignment
- `eng-jpn-align.tsv` -- English-Japanese alignment
- `eng-ind-align.tsv` -- English-Indonesian alignment
- `ntu-mc-id.tab` -- ID mapping

### `sents/` -- Tab-delimited sentence exports (1451 files)

Per-corpus, per-language sentence dumps.  Includes:
- `essay-{eng,cmn,jpn}-catb.tab` -- essay sentences in all 3 languages
- `kc-{eng,cmn,jpn}-kc0{1,2}.tab` -- news sentences
- `story-{eng,cmn,jpn}-{danc,spec}.tab` -- story sentences
- `yoursing-{cmn,eng,...}-*.tab` -- yoursing per-document sentences

### Top-level files

- **Fix scripts**: `fix-meta.py`, `fix-story.py`, `fix-tags-cmn.py`,
  `fix-tags-ind.py`, `fix-ind-sc.py`, `fix-cfrom.py`, `fix-trust.py`,
  `renumber.py` -- various data-cleaning scripts from 2013
- **Link scripts**: `link-essay.py`, `link-story.py`, `link-sb.py`,
  `link-yoursing.py`, `link-concepts.py`, `link-tradicorp.py` --
  cross-lingual linking tools
- **Analysis**: `analyze.py`, `analyze-links.py`, `analyze-errors.py`,
  `sum.py`, `db2semcor.py`
- **Error reports**: `{eng,cmn,jpn,ind}-err-list.tsv` -- annotation error lists
- **Unknown word lists**: `cmn-unk.tsv`, `ind-unk.tsv` -- words not in wordnet
- `ind-yoursing.db` -- old-format Indonesian yoursing (2197 sents; live has 3098)

---

## Recommended Actions (Priority Order)

### P1: Merge missing corpora into live databases

1. **eng essay (catb)**: Merge `2014-04-04/eng-essay.db` (or `round0/eng-catb.db`)
   into live eng.db.  Needs: add corpus row (corpusID=4, 'essay'), create doc row,
   convert old schema (no cwl) to new schema, renumber sids from 101--869 to 1--769
   (to match the manual's convention).

2. **jpn essay (catb)**: Merge `2014-04-04/jpn-essay.db` into live jpn.db.
   Sids 1--773 already in the correct range.  Needs schema conversion.

3. **jpn kc (news)**: Merge `round0/jpn-kc.db` into live jpn.db.
   Needs sid renumbering from 100000+ to 60000+ and schema conversion.

### P2: Import missing stype data

4. **cmn yoursing stype**: Import `alvas/stype.tab` (3280 entries, H→h0/h1, P→p).

5. **eng yoursing stype**: Infer h0 from first sentence of each doc (done in
   fix_corpus.py); consider inferring more from yoursing page structure.

6. **eng kc stype**: The news corpus may not have natural paragraph structure.
   Needs investigation.

### P3: Verify cross-lingual links

7. Compare link DBs in `2013-10-05/` against live `eng-cmn.db`, `eng-jpn.db`,
   `eng-ind.db` on the server to ensure all links were migrated.
