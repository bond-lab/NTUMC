# NTU-MC Scripts

Scripts for building, testing, and maintaining the NTU Multilingual Corpus
release artifacts.

## Release workflow

**`release.sh`** — End-to-end release pipeline.

```
./release.sh [OPTIONS] VERSION

Options:
  --skip-download   Skip the scp download step
  --build-only      Stop after processing (inspect build/ before releasing)
  --draft           Create GitHub release as a draft
```

Downloads databases from the server, extracts frequencies/sentiment/wordnets,
adds pinyin, drops log tables, compresses with xz, and creates a GitHub
release.  Use `--build-only` to inspect `build/` before publishing.


## Wordnet extraction

**`getwn.py`** — Extract WN-LMF XML wordnets from `wn-ntumc.db`.

```
.venv/bin/python scripts/getwn.py WN_DB OUTDIR [--lang LANG ...] \
    [--ili ILI_MAP] [--version VER] [--base omw-en:2.0]
```

Produces one `wn-ntumc-LANG.xml` file per language.  Filters against a
base wordnet to emit only new/changed content.  Validates each output and
writes a log to `--output-file`.

**`addpinyin.py`** — Add pinyin pronunciations to the Chinese wordnet XML.

```
.venv/bin/python scripts/addpinyin.py CEDICT_GZ CMN_XML \
    [--db WN_DB] [--ambiguous TSV]
```

Uses CC-CEDICT to assign pinyin to Chinese lemmas via multi-stage
disambiguation (gloss matching, pronunciation notes, Taiwan
cross-references).  Writes ambiguous cases to a TSV for review.


## Database maintenance

**`fixwn.py`** — Fix validation issues in `wn-ntumc.db`.

```
.venv/bin/python scripts/fixwn.py WN_DB [--dry-run]
```

Fixes self-loops (W502), POS-mismatch hypernyms (W501) by renaming synsets,
deleting bad links, removing compositional synsets, and merging duplicates.

**`fixlinks.py`** — Fix synlink errors and list orphan synsets.

```
.venv/bin/python scripts/fixlinks.py WN_DB [--dry-run]
```

Removes duplicate synlink rows (W403), adds missing reverse relations (W404),
and lists orphan synsets (synsets with no senses in any language).

To fix the upstream database:

```
scp compling.upol.cz:/var/www/ntumc/db/wn-ntumc.db /tmp/wn-ntumc.db
.venv/bin/python scripts/fixlinks.py /tmp/wn-ntumc.db
scp /tmp/wn-ntumc.db compling.upol.cz:/var/www/ntumc/db/wn-ntumc.db
```


## Log management

**`droplogs.sh`** — Drop all `*_log` tables from database files and VACUUM.

```
scripts/droplogs.sh DB [DB ...]
```

Used on the copies in `build/` during the release pipeline (integrated into
`release.sh`).  Does not touch the server originals.

**`rotate-logs.sh`** — Archive old log rows on the server.

```
scripts/rotate-logs.sh [OPTIONS]

Options:
  --db-dir DIR     Database directory (default: /var/www/ntumc/db)
  --cutoff DATE    Archive rows before this date (default: 1 year ago)
  --archive FILE   Archive DB path (default: DB_DIR/logs-before-CUTOFF.db)
  --apply          Actually delete rows (default: dry-run only)
```

Copies rows with `date_update` older than the cutoff into an archive database
(`logs-before-YYYY-MM-DD.db`), then deletes them from the source and VACUUMs.
Skips annotator-split variants (A–E databases).  **Defaults to dry-run** —
pass `--apply` to actually modify the source databases.

To run on the server over SSH:

```
# Dry run (creates archive, reports what would be deleted, no changes)
ssh compling.upol.cz 'bash -s' < scripts/rotate-logs.sh

# Apply (deletes old rows from source databases)
ssh compling.upol.cz 'bash -s -- --apply' < scripts/rotate-logs.sh
```


## Frequency and sentiment extraction

**`getfreq.sh`** — Extract concept frequencies as TSV.

```
scripts/getfreq.sh CORPUS.db [OUTPUT.tsv]
```

**`getsenti.sh`** — Extract concept sentiment as TSV (one file per corpus).

```
scripts/getsenti.sh CORPUS.db [OUTDIR]
```


## Testing

**`test_build.py`** — Verify built XML wordnets match the source database.

```
.venv/bin/python scripts/test_build.py WN_DB BUILDDIR \
    [--lang LANG ...] [--base omw-en:2.0]
```

Checks that entry, sense, and synset counts in each XML file are consistent
with the database under the same filtering conditions used by `getwn.py`.


## Utilities

**`find_merge_candidates.py`** — Find lemmas differing only by
whitespace/hyphens that share identical senses (candidates for merging
into a single entry with variant forms).

```
.venv/bin/python scripts/find_merge_candidates.py WN_DB LANG [LANG ...]
.venv/bin/python scripts/find_merge_candidates.py wordnet.xml
```

**`merge_bahasa.py`** — Merge NTU-MC wordnet XML with Bahasa Wordnet tab
data (confidence filtering and Indonesian definitions).

```
.venv/bin/python scripts/merge_bahasa.py NTUMC_XML TAB_DIR [-o OUTPUT]
```

**`db2tsdb.py`** — Export a corpus as a DELPH-IN TSDB profile.

**`dump_doc.py`** — Dump document JSON from an NTU-MC corpus database.
