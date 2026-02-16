#!/usr/bin/env bash
### This is a script for making a release of the NTU-MC data
###
###  * Download from the current server (db, links, wordnet)
###  * Extract frequencies, sentiment, and wordnets
###  * Compress all databases with xz
###  * Create a GitHub release with gh
###
### Usage: ./release.sh [OPTIONS] VERSION
###
###   VERSION   Release tag, e.g. 2026.02
###
### Options:
###   --skip-download   Skip the scp download step
###   --build-only      Stop after processing (inspect build/ before releasing)
###   --draft           Create GitHub release as a draft
###   --help            Show this help message
###

set -euo pipefail

# ── cd to repo root (one level up from scripts/) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

BUILDDIR="build"
LOGDIR="${BUILDDIR}/log"
PYTHON=".venv/bin/python"
mkdir -p "$BUILDDIR" "$LOGDIR"

# ── Corpus & wordnet databases ──
CORPUS_DBS=(eng.db ces.db ita.db cmn.db yue.db ind.db zsm.db jpn.db)
WORDNET_DBS=(wn-ntumc.db wn-multix.db)
ALL_DBS=("${CORPUS_DBS[@]}" "${WORDNET_DBS[@]}")

SCP_HOST="compling.upol.cz"
SCP_PATH="/var/www/ntumc/db"

# ── Argument parsing ──
SKIP_DOWNLOAD=0
BUILD_ONLY=0
DRAFT=0
VERSION=""

usage() {
    sed -n 's/^### //p; s/^###$//p' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-download) SKIP_DOWNLOAD=1; shift ;;
        --build-only)    BUILD_ONLY=1; shift ;;
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

# ── 2. Process ──
echo "--- Extracting concept frequencies ---"
for db in "${CORPUS_DBS[@]}"; do
    src="${BUILDDIR}/${db}"
    if [[ ! -f "$src" ]]; then
        echo "  WARNING: $src not found, skipping"
        continue
    fi
    tsv=$("$SCRIPT_DIR/getfreq.sh" "$src")
    echo "  $(basename "$tsv")"
done

echo "--- Extracting sentiment ---"
for db in "${CORPUS_DBS[@]}"; do
    src="${BUILDDIR}/${db}"
    if [[ ! -f "$src" ]]; then
        echo "  WARNING: $src not found, skipping"
        continue
    fi
    while IFS= read -r tsv; do
        echo "  $(basename "$tsv")"
    done < <("$SCRIPT_DIR/getsenti.sh" "$src")
done

echo "--- Building wordnets ---"
"$PYTHON" "$SCRIPT_DIR/getwn.py" \
    "${BUILDDIR}/wn-ntumc.db" "$BUILDDIR" \
    --output-file "$LOGDIR/validate-wn.txt"
echo "  Validation log: $LOGDIR/validate-wn.txt"

if [[ "$BUILD_ONLY" -eq 1 ]]; then
    echo "=== Build complete (--build-only). Inspect $BUILDDIR/ before releasing. ==="
    exit 0
fi

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
for f in "$BUILDDIR"/wn-freq-*-ntumc.tsv \
         "$BUILDDIR"/wn-senti-*-ntumc.tsv \
         "$BUILDDIR"/wn-ntumc-*.xml; do
    [[ -f "$f" ]] && ASSETS+=("$f")
done

GH_ARGS=(gh release create "$VERSION" --generate-notes)
if [[ "$DRAFT" -eq 1 ]]; then
    GH_ARGS+=(--draft)
fi
GH_ARGS+=("${ASSETS[@]}")

echo "  Running: ${GH_ARGS[*]}"
"${GH_ARGS[@]}"

echo "=== Done ==="
