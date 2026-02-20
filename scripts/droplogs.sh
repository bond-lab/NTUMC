#!/usr/bin/env bash
### Drop all *_log tables from database files and VACUUM.
###
### Usage: droplogs.sh DB [DB ...]
###
### This is meant for release copies in build/, not the server originals.

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 DB [DB ...]" >&2
    exit 1
fi

for db in "$@"; do
    if [[ ! -f "$db" ]]; then
        echo "SKIP: $db not found"
        continue
    fi

    tables=$(sqlite3 "$db" \
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%_log' ORDER BY name")

    if [[ -z "$tables" ]]; then
        echo "$(basename "$db"): no log tables"
        continue
    fi

    before=$(stat -c%s "$db")
    sql=""
    count=0
    for t in $tables; do
        sql+="DROP TABLE IF EXISTS \"$t\";"
        count=$((count + 1))
    done
    sql+="VACUUM;"

    sqlite3 "$db" "$sql"
    after=$(stat -c%s "$db")
    saved=$(( (before - after) / 1048576 ))
    printf "%-20s  dropped %d log tables  %dM -> %dM  (saved %dM)\n" \
        "$(basename "$db")" "$count" "$((before/1048576))" "$((after/1048576))" "$saved"
done
