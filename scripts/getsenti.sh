#!/usr/bin/env bash
### Extract concept sentiment from an NTU-MC corpus database.
###
### Outputs one TSV per corpus: wn-senti-LANG-CORPUS-ntumc.tsv
### Includes zero sentiment (NULL -> 0) but only for documents
### with at least 10 sentiment-annotated concepts.
###
### Usage: getsenti.sh CORPUS.db [OUTDIR]
###
###   OUTDIR defaults to the directory containing CORPUS.db.
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
OUTDIR="${2:-$(dirname "$DB")}"
TODAY=$(date +%Y-%m-%d)

# Skip databases without a sentiment table
if ! sqlite3 "$DB" "SELECT 1 FROM sentiment LIMIT 1;" 2>/dev/null; then
    exit 0
fi

sqlite3 "$DB" "SELECT corpusID, corpus FROM corpus;" | while IFS='|' read -r cid cname; do
    TSV="${OUTDIR}/wn-senti-${LANG}-${cname}-ntumc.tsv"
    {
        printf "# Sentiment for %s/%s from ntu-mc (%s)\n" "$LANG" "$cname" "$TODAY"
        printf "synset\tlemma\tmean_sentiment\tfreq\n"
        sqlite3 -separator '	' "$DB" "
            WITH eligible_docs AS (
                SELECT d.docid
                FROM doc d
                JOIN sent s ON d.docid = s.docid
                JOIN sentiment st ON s.sid = st.sid
                WHERE d.corpusID = $cid
                GROUP BY d.docid
                HAVING COUNT(*) >= 10
            )
            SELECT c.tag, c.clemma,
                   ROUND(AVG(COALESCE(st.score, 0)), 4),
                   COUNT(*)
            FROM concept c
            JOIN sent s ON c.sid = s.sid
            JOIN doc d ON s.docid = d.docid
            JOIN eligible_docs ed ON d.docid = ed.docid
            LEFT JOIN sentiment st ON c.sid = st.sid AND c.cid = st.cid
            WHERE c.tag NOT IN ('x', 'w', 'e')
            GROUP BY c.tag, c.clemma
            ORDER BY c.tag;"
    } > "$TSV"

    # Remove empty files (header-only = no eligible docs)
    if [[ $(wc -l < "$TSV") -le 2 ]]; then
        rm -f "$TSV"
    else
        echo "$TSV"
    fi
done
