#!/usr/bin/env bash
### Extract concept frequencies from an NTU-MC corpus database.
###
### Usage: getfreq.sh CORPUS.db [OUTPUT.tsv]
###
###   If OUTPUT.tsv is omitted, writes to wn-freq-LANG-ntumc.tsv
###   in the same directory as CORPUS.db.
###

set -euo pipefail

if [[ $# -lt 1 || "$1" == "--help" || "$1" == "-h" ]]; then
    sed -n 's/^### //p; s/^###$//p' "$0"
    exit 0
fi

DB="$1"
if [[ ! -f "$DB" ]]; then
    echo "Error: $DB not found" >&2
    exit 1
fi

LANG=$(basename "$DB" .db)
DIR=$(dirname "$DB")
TSV="${2:-${DIR}/wn-freq-${LANG}-ntumc.tsv}"

{
    printf "# Frequency for %s from ntu-mc (%s)\n" "$LANG" "$(date +%Y-%m-%d)"
    printf "synset\tlemma\tfreq\n"
    sqlite3 -separator '	' "$DB" \
        "SELECT tag, clemma, COUNT(clemma)
         FROM concept
         WHERE LENGTH(tag) = 10
         GROUP BY tag, clemma;"
} > "$TSV"

echo "$TSV"
