#!/usr/bin/env bash
# Build the corpus and wordnet site: the corpus display, with the
# wordnets (a Cygnet build) under wordnet/, each linked to the other.
#
#   bash scripts/build_site.sh [--no-wordnet] [--no-display]
#
# Needs, already built: the corpus databases (build/LANG.db), the
# wordnets named in scripts/site/wordnets.toml, and
# ntumc-en's minimal lexicon ($NTUMC_EN).  CYGNET is a checkout of
# Cygnet that links synsets by dc:identifier and shows corpus links.
#
# The site is display/; serve it with scripts/serve_site.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CYGNET="${CYGNET:-$ROOT/../cygnet}"
NTUMC_EN="${NTUMC_EN:-$ROOT/../omw-ntumc/english/release/ntumc-en-min-0.1.xml}"
WORK="$ROOT/build/site/wordnet-work"
PY="$ROOT/.venv/bin/python"
LANGS=(eng cmn jpn ind ita ces)

wordnet=1 display=1
for arg in "$@"; do
    case "$arg" in
        --no-wordnet) wordnet=0 ;;
        --no-display) display=0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

cd "$ROOT"
mkdir -p "$WORK"
[[ -f "$WORK/wordnets.toml" ]] || cp scripts/site/wordnets.toml "$WORK/wordnets.toml"

if (( display )); then
    for lang in "${LANGS[@]}"; do
        "$PY" scripts/make_display.py --lang "$lang" --all
    done
    "$PY" scripts/make_display.py --build-pages
    "$PY" scripts/make_display.py --build-json
fi
# always: it writes the definitions and words from the wordnet database,
# which make_concordance.py compares with the new wordnets and replaces
"$PY" scripts/make_display.py --build-data

if (( wordnet )); then
    "$PY" scripts/english_additions.py "$NTUMC_EN" "$WORK/ntumc-en-additions.xml"
    # Cygnet keeps what it fetched and converted, by file name.  Our own
    # wordnets change without a new name, so their copies are removed first.
    if [[ -f "$WORK/bin/raw_wns/sources.tsv" ]]; then
        grep '^file://' "$WORK/bin/raw_wns/sources.tsv" | cut -f2 | while read -r name; do
            rm -f "$WORK/bin/raw_wns/$name"
        done
        find "$WORK/bin/cygnets_presynth" -maxdepth 1 -name '*.xml' \
            ! -name 'oewn-*' ! -name 'cili-*' ! -name 'omw-kin-*' ! -name 'omw-pronoun-*' -delete
    fi
    (cd "$CYGNET" && bash build.sh --work-dir "$WORK")
fi
cp "$CYGNET/web/index.html" "$CYGNET/web/relations.json" "$WORK/web/"
cp scripts/site/local.json "$WORK/web/local.json"

"$PY" scripts/make_concordance.py --wordnet "$WORK/web"
ln -sfn "$WORK/web" display/wordnet
echo "Built display/ (wordnets: display/wordnet -> $WORK/web)"
