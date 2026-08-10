#!/usr/bin/env bash
### Rotate old log rows from NTU-MC databases into an archive DB.
###
### For each database in DB_DIR, copies rows from *_log tables with
### date_update < CUTOFF into an archive database, then (only with
### --apply) deletes those rows from the source and vacuums.
###
### Usage: rotate-logs.sh [OPTIONS]
###
### Options:
###   --db-dir DIR     Database directory (default: /var/www/ntumc/db)
###   --cutoff DATE    Archive rows before this date (default: 1 year ago)
###   --archive FILE   Archive database path (default: DB_DIR/logs-before-CUTOFF.db)
###   --apply          Actually delete rows (default: dry-run only)
###   --help           Show this help message
###
### Without --apply, this only reports what would happen and creates the
### archive DB.  The source databases are NEVER modified without --apply.

set -euo pipefail

DB_DIR="/var/www/ntumc/db"
CUTOFF=""
ARCHIVE=""
APPLY=0

usage() {
    sed -n 's/^### //p; s/^###$//p' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db-dir)    DB_DIR="$2"; shift 2 ;;
        --cutoff)    CUTOFF="$2"; shift 2 ;;
        --archive)   ARCHIVE="$2"; shift 2 ;;
        --apply)     APPLY=1; shift ;;
        --help|-h)   usage ;;
        *)           echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# Default cutoff: 1 year ago
if [[ -z "$CUTOFF" ]]; then
    CUTOFF=$(date -d "1 year ago" +%Y-%m-%d 2>/dev/null \
          || date -v-1y +%Y-%m-%d)
fi

if [[ -z "$ARCHIVE" ]]; then
    ARCHIVE="${DB_DIR}/logs-before-${CUTOFF}.db"
fi

if [[ "$APPLY" -eq 0 ]]; then
    echo "=== DRY RUN (pass --apply to delete from source databases) ==="
else
    echo "=== APPLY MODE: will delete old rows from source databases ==="
fi
echo "  DB directory: $DB_DIR"
echo "  Cutoff:       $CUTOFF (archiving rows older than this)"
echo "  Archive:      $ARCHIVE"
echo

total_archived=0
total_to_delete=0

for db in "$DB_DIR"/*.db; do
    [[ -f "$db" ]] || continue
    dbname=$(basename "$db")

    # Skip the archive DB itself
    [[ "$db" = "$ARCHIVE" ]] && continue

    # Skip annotator-split variants (e.g. engA.db … engE.db)
    [[ "$dbname" =~ ^[a-z]+[A-E]\.db$ ]] && continue

    # Find log tables
    tables=$(sqlite3 "$db" \
        "SELECT name FROM sqlite_master
         WHERE type='table' AND name LIKE '%_log'
         ORDER BY name" 2>/dev/null) || continue

    [[ -z "$tables" ]] && continue

    has_old=0
    for t in $tables; do
        old_count=$(sqlite3 "$db" \
            "SELECT COUNT(*) FROM \"$t\" WHERE date_update < '$CUTOFF'")
        if [[ "$old_count" -gt 0 ]]; then
            has_old=1
            break
        fi
    done
    [[ "$has_old" -eq 0 ]] && continue

    echo "--- $dbname ---"

    for t in $tables; do
        total=$(sqlite3 "$db" "SELECT COUNT(*) FROM \"$t\"")
        old_count=$(sqlite3 "$db" \
            "SELECT COUNT(*) FROM \"$t\" WHERE date_update < '$CUTOFF'")

        if [[ "$old_count" -eq 0 ]]; then
            continue
        fi

        remaining=$((total - old_count))
        printf "  %-25s %8d old / %8d total  (keep %d)\n" \
            "$t" "$old_count" "$total" "$remaining"

        # Copy schema to archive (if not already there)
        # Use source_db.table naming with ATTACH
        schema=$(sqlite3 "$db" \
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='$t'")

        # Prefix table name with db name to avoid collisions
        archive_table="${dbname%.db}__${t}"
        archive_schema=$(echo "$schema" | sed "s/CREATE TABLE \"*${t}\"*/CREATE TABLE IF NOT EXISTS \"${archive_table}\"/")

        sqlite3 "$ARCHIVE" "$archive_schema"

        # Copy old rows to archive
        cols=$(sqlite3 "$db" "PRAGMA table_info(\"$t\")" \
            | cut -d'|' -f2 | paste -sd,)

        # Clear any previous partial archive for this table, then copy
        sqlite3 "$ARCHIVE" "DELETE FROM \"$archive_table\" WHERE 1;
            ATTACH '$db' AS src;
            INSERT INTO \"$archive_table\" SELECT * FROM src.\"$t\"
            WHERE date_update < '$CUTOFF';
            DETACH src;"

        # Verify count in archive
        archived=$(sqlite3 "$ARCHIVE" \
            "SELECT COUNT(*) FROM \"$archive_table\"
             WHERE date_update < '$CUTOFF'")

        if [[ "$archived" -lt "$old_count" ]]; then
            echo "    ERROR: archive has $archived rows but source has $old_count — SKIPPING delete"
            continue
        fi

        total_archived=$((total_archived + old_count))
        total_to_delete=$((total_to_delete + old_count))

        if [[ "$APPLY" -eq 1 ]]; then
            sqlite3 "$db" "DELETE FROM \"$t\" WHERE date_update < '$CUTOFF'"
            deleted=$(sqlite3 "$db" "SELECT changes()")
            echo "    -> deleted $old_count rows from source"
        fi
    done

    if [[ "$APPLY" -eq 1 ]]; then
        before=$(stat -c%s "$db" 2>/dev/null || stat -f%z "$db")
        sqlite3 "$db" "VACUUM"
        after=$(stat -c%s "$db" 2>/dev/null || stat -f%z "$db")
        saved=$(( (before - after) / 1024 ))
        echo "  VACUUM: saved ${saved}K"
    fi
done

echo
archive_size=0
if [[ -f "$ARCHIVE" ]]; then
    archive_size=$(stat -c%s "$ARCHIVE" 2>/dev/null || stat -f%z "$ARCHIVE")
fi
echo "Archive: $ARCHIVE ($(( archive_size / 1048576 ))M)"
echo "Total rows archived: $total_archived"

if [[ "$APPLY" -eq 0 ]]; then
    echo
    echo "This was a dry run. The archive DB has been created but NO rows"
    echo "were deleted from source databases. Re-run with --apply to delete."
else
    echo "Total rows deleted from source: $total_to_delete"
fi
