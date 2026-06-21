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

**`fix_corpus.py`** — Audit and fix corpus metadata (corpus table, doc.corpusID,
stype) across all language databases.

```
# Audit only (report issues, no changes)
.venv/bin/python scripts/fix_corpus.py --audit

# Download fresh copies from server and audit
.venv/bin/python scripts/fix_corpus.py --download --audit

# Apply fixes (dry run first)
.venv/bin/python scripts/fix_corpus.py --fix --dry-run --audit
.venv/bin/python scripts/fix_corpus.py --fix --audit

# Push fixed databases back to server (interactive confirmation)
.venv/bin/python scripts/fix_corpus.py --push
```

Automated fixes:
- Missing corpus table rows (e.g. ind corpusID=3 for stories)
- NULL language in corpus table (ces, yue)
- Missing stype `h0` entries for YourSingapore document titles

Issues requiring manual work (reported as TODO):
- stype entries for essay, news (kc), and story corpora
- Empty corpus placeholders (corpus rows with no documents)

**`fix_catb_stype.py`** — Fix stype annotations for *The Cathedral and the
Bazaar* by downloading the original HTML from catb.org and extracting paragraph
boundaries.  Sets `p` only on the first sentence of each paragraph (remaining
sentences get no stype and flow inline).  Also sets `h1`, `h2`, `author`, and
`item` (for the 19 numbered lessons).  Propagates to jpn and cmn via slinks.

```
.venv/bin/python scripts/fix_catb_stype.py --dry-run
.venv/bin/python scripts/fix_catb_stype.py --fix
```

**`propagate_stype.py`** — Propagate stype annotations from English to other
languages via sentence links (slinks).

```
# Dry run (report what would change)
.venv/bin/python scripts/propagate_stype.py --dry-run

# Apply
.venv/bin/python scripts/propagate_stype.py --fix
```

Uses slink tables in `eng-{lang}.db` to map English stypes to target languages.
For 1:many sentence links (one English sentence split into several in the
target), only the first target sentence gets the stype.  For tourism documents
(sid >= 100000) which share sid ranges across languages, stypes are copied
directly by sid.  Only inserts where the target has no existing stype.

**`merge_old_corpora.py`** — Merge corpora left behind when the project
switched from per-genre to per-language databases (~2015).

```
# Dry run (report what would change)
.venv/bin/python scripts/merge_old_corpora.py --fix --dry-run

# Apply merges to local build/ copies
.venv/bin/python scripts/merge_old_corpora.py --fix

# Download fresh copies from server first
.venv/bin/python scripts/merge_old_corpora.py --download --fix
```

Merges three missing corpora with schema conversion (old concept+wid →
new concept+cwl):
- English essay (catb): 769 sents from `work/ntu-mc/2014-04-04/eng-essay.db`
- Japanese essay (catb): 773 sents from `work/ntu-mc/2014-04-04/jpn-essay.db`
- Japanese news (kc01+kc02): 2020 sents from `work/ntu-mc/2013-10-05/jpn-kc.db`

Also imports Chinese yoursing stype data (2970 entries) from
`work/ntu-mc/alvas/stype.tab`.


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


## Corpus display

**`make_display.py`** — Generate self-contained static HTML pages for corpus
documents, suitable for second-language learners and researchers.  Each page
embeds POS tags, synset definitions, and synonyms as inline JSON so it works
from `file://` without a local server.  Hovering a tagged word shows a tooltip
with its lemma, POS badge, synset definition, and English synonyms; MWEs are
highlighted in yellow.

```
.venv/bin/python scripts/make_display.py --lang eng --doc spec --outdir display/
.venv/bin/python scripts/make_display.py --lang eng --all --outdir display/
.venv/bin/python scripts/make_display.py --lang eng --all --tagged --outdir display/
```

Options:
- `--lang LANG` — corpus language (default: `eng`)
- `--doc NAME` / `--docid ID` / `--all` — which document(s) to process
- `--tagged` — only include documents with ≥ `--min-tagged` fraction of words tagged
- `--min-tagged FRAC` — threshold for `--tagged` (default: 0.5).  Auto-lowered
  to the minimum non-zero rate when the language's best rate falls below this
  value, so all tagged documents are still included.
- `--outdir DIR` — output directory (default: `display/`)

Each run saves `display/{lang}/index.json` (per-language metadata sidecar).
The combined `display/index.html` is rebuilt from all sidecars after every run,
so you can run the script per language and the index accumulates automatically.
The index uses language tabs (sorted by document count) with collapsible
corpus/genre groups inside each tab.

To regenerate all tagged corpora:
```
for lang in eng cmn ind ita ces; do
    .venv/bin/python scripts/make_display.py --lang $lang --all --tagged --outdir display/
done
# Japanese needs a lower threshold (kc02 is only 3% tagged)
.venv/bin/python scripts/make_display.py --lang jpn --all --tagged --min-tagged 0.01 --outdir display/
```

### Full rebuild from scratch

Download fresh databases, apply all fixes, and regenerate the display:

```
# 1. Download databases from the server
.venv/bin/python scripts/fix_corpus.py --download

# 2. Apply corpus metadata fixes (missing corpus rows, stype h0, NULL language)
.venv/bin/python scripts/fix_corpus.py --fix

# 3. Merge missing corpora from old per-genre databases
#    (eng essay, jpn essay, jpn kc, cmn stype)
.venv/bin/python scripts/merge_old_corpora.py --fix

# 4. Propagate stype from English to other languages via slinks
.venv/bin/python scripts/propagate_stype.py --fix

# 5. Audit to verify
.venv/bin/python scripts/fix_corpus.py --audit

# 6. Regenerate display HTML
for lang in eng cmn ind ita ces; do
    .venv/bin/python scripts/make_display.py --lang $lang --all --tagged --outdir display/
done
.venv/bin/python scripts/make_display.py --lang jpn --all --tagged --min-tagged 0.01 --outdir display/

# 7. Review, then push back to server when satisfied
#    .venv/bin/python scripts/fix_corpus.py --push
```

**`fix_cpos.py`** — Populate missing `cfrom`/`cto` character offsets in the
`word` table by scanning each sentence's text left-to-right.  These offsets are
used by `make_display.py` to determine whether a space follows each word.

```
.venv/bin/python scripts/fix_cpos.py build/eng.db
.venv/bin/python scripts/fix_cpos.py build/eng.db --docid 440
.venv/bin/python scripts/fix_cpos.py build/eng.db --dry-run
```


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
