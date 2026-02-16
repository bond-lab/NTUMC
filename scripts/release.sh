#!/usr/bin/env bash
### This is a script for making a release of the NTU-MC data
###
###  * Download from the current server (db, links, wordnet)
###  * Create wordnets from server (dump from db, add counts from corpora)
###  * Compress all databases with xz
###  * Create a GitHub release with gh
###
### Usage: ./release.sh [OPTIONS] VERSION
###
###   VERSION   Release tag, e.g. 2026.02
###
### Options:
###   --skip-download   Skip the scp download step
###   --draft           Create GitHub release as a draft
###   --help            Show this help message
###

set -euo pipefail

# ── cd to repo root (one level up from scripts/) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

BUILDDIR="build"
mkdir -p "$BUILDDIR"

# ── Corpus & wordnet databases ──
CORPUS_DBS=(eng.db ces.db ita.db cmn.db yue.db ind.db zsm.db jpn.db)
WORDNET_DBS=(wn-ntumc.db wn-multix.db)
ALL_DBS=("${CORPUS_DBS[@]}" "${WORDNET_DBS[@]}")

SCP_HOST="compling.upol.cz"
SCP_PATH="/var/www/ntumc/db"

# ── Argument parsing ──
SKIP_DOWNLOAD=0
DRAFT=0
VERSION=""

usage() {
    sed -n 's/^### //p; s/^###$//p' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-download) SKIP_DOWNLOAD=1; shift ;;
        --draft)         DRAFT=1; shift ;;
        --help|-h)       usage ;;
        -*)              echo "Unknown option: $1" >&2; exit 1 ;;
        *)               VERSION="$1"; shift ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    echo "Error: VERSION argument is required." >&2
    echo "Usage: $0 [OPTIONS] VERSION" >&2
    exit 1
fi

echo "=== NTU-MC Release $VERSION ==="
echo "Build directory: $BUILDDIR"

# ── 1. Download ──
if [[ "$SKIP_DOWNLOAD" -eq 1 ]]; then
    echo "--- Skipping download (--skip-download) ---"
else
    echo "--- Downloading databases from $SCP_HOST ---"
    for db in "${ALL_DBS[@]}"; do
        echo "  $db"
        scp "${SCP_HOST}:${SCP_PATH}/${db}" "${BUILDDIR}/"
    done
fi

# ── 2. Process: extract concept frequencies ──
echo "--- Extracting concept frequencies ---"
TODAY=$(date +%Y-%m-%d)
for db in "${CORPUS_DBS[@]}"; do
    lang="${db%.db}"
    src="${BUILDDIR}/${db}"
    tsv="${BUILDDIR}/wn-freq-${lang}-ntumc.tsv"
    if [[ ! -f "$src" ]]; then
        echo "  WARNING: $src not found, skipping"
        continue
    fi
    echo "  $lang -> $(basename "$tsv")"
    {
        printf "# Frequency for %s from ntu-mc (%s)\n" "$lang" "$TODAY"
        printf "synset\tlemma\tfreq\n"
        sqlite3 -separator '	' "$src" \
            "SELECT tag, clemma, COUNT(clemma)
             FROM concept
             WHERE LENGTH(tag) = 10
             GROUP BY tag, clemma;"
    } > "$tsv"
done

# ── 3. Compress ──
echo "--- Compressing databases ---"
for db in "${ALL_DBS[@]}"; do
    src="${BUILDDIR}/${db}"
    dst="${src}.xz"
    if [[ ! -f "$src" ]]; then
        echo "  WARNING: $src not found, skipping"
        continue
    fi
    if [[ -f "$dst" && "$dst" -nt "$src" ]]; then
        echo "  $db.xz is up to date, skipping"
        continue
    fi
    echo "  compressing $db ..."
    xz -k -9 -f "$src"
done

# ── 4. Create GitHub release ──
echo "--- Creating GitHub release $VERSION ---"

ASSETS=()
for db in "${ALL_DBS[@]}"; do
    asset="${BUILDDIR}/${db}.xz"
    if [[ -f "$asset" ]]; then
        ASSETS+=("$asset")
    else
        echo "  WARNING: $asset not found, will not be included"
    fi
done
for db in "${CORPUS_DBS[@]}"; do
    lang="${db%.db}"
    tsv="${BUILDDIR}/wn-freq-${lang}-ntumc.tsv"
    if [[ -f "$tsv" ]]; then
        ASSETS+=("$tsv")
    fi
done

GH_ARGS=(gh release create "$VERSION" --generate-notes)
if [[ "$DRAFT" -eq 1 ]]; then
    GH_ARGS+=(--draft)
fi
GH_ARGS+=("${ASSETS[@]}")

echo "  Running: ${GH_ARGS[*]}"
"${GH_ARGS[@]}"

echo "=== Done ==="
