#!/usr/bin/env bash
# push_dbs.sh
#
# Push fixed corpus databases from build/ back to the compling server,
# taking a dated server-side backup of each database first.
#
# Usage: ./push_dbs.sh [OPTIONS] [DB ...]
#   DB          Database basename(s) without path, e.g. eng.db cmn.db.
#               Default: eng.db cmn.db jpn.db ind.db ita.db ces.db wn-ntumc.db
#
# Options:
#   --host HOST   SSH host (default: compling.upol.cz)
#   --dry-run     Show what would happen without copying anything
#   --yes         Skip the interactive confirmation
#
# Safety: refuses to push a database whose local copy has no *_log
# tables (that would erase the server's annotation history — see
# docs/release-audit-2026-07-05.md).  Verifies each upload by comparing
# remote and local SHA-256 checksums.

set -euo pipefail

HOST="compling.upol.cz"
REMOTE_DIR="/var/www/ntumc/db"
BUILD_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/build"
BACKUP_SUBDIR="backup-$(date +%Y-%m-%d)"
DRY_RUN=0
ASSUME_YES=0
DBS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)    HOST="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        --yes)     ASSUME_YES=1; shift ;;
        -*)        echo "Unknown option: $1" >&2; exit 1 ;;
        *)         DBS+=("$1"); shift ;;
    esac
done

if [[ ${#DBS[@]} -eq 0 ]]; then
    DBS=(eng.db cmn.db jpn.db ind.db ita.db ces.db wn-ntumc.db)
fi

command -v sqlite3 >/dev/null 2>&1 || {
    echo "Error: sqlite3 is required" >&2; exit 1; }

# ── validate local copies ──
for db in "${DBS[@]}"; do
    local_path="${BUILD_DIR}/${db}"
    if [[ ! -f "$local_path" ]]; then
        echo "Error: ${local_path} not found" >&2
        exit 1
    fi
    # a copy without log tables is a stripped release copy, not a
    # server-grade database
    n_logs=$(sqlite3 "$local_path" \
        "SELECT COUNT(*) FROM sqlite_master
         WHERE type='table' AND name LIKE '%_log'")
    if [[ "$n_logs" -eq 0 ]]; then
        echo "Error: ${db} has no *_log tables — pushing it would erase" >&2
        echo "the server's annotation history. Re-download and re-apply" >&2
        echo "fixes instead (see docs/release-audit-2026-07-05.md)." >&2
        exit 1
    fi
done

echo "Will push to ${HOST}:${REMOTE_DIR} (backup in ${BACKUP_SUBDIR}/):"
for db in "${DBS[@]}"; do
    printf '  %-14s %s\n' "$db" \
        "$(du -h "${BUILD_DIR}/${db}" | cut -f1)"
done

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Dry run: nothing copied."
    exit 0
fi

if [[ "$ASSUME_YES" -ne 1 ]]; then
    read -r -p "Proceed? [y/N] " answer
    [[ "${answer,,}" == "y" ]] || { echo "Aborted."; exit 1; }
fi

# ── server-side backup ──
echo "--- Backing up server copies to ${REMOTE_DIR}/${BACKUP_SUBDIR} ---"
# shellcheck disable=SC2029  # server-side expansion is intended
ssh "$HOST" "mkdir -p '${REMOTE_DIR}/${BACKUP_SUBDIR}'"
for db in "${DBS[@]}"; do
    echo "  $db"
    # -n: never overwrite an existing backup from the same day
    ssh "$HOST" "cp -n '${REMOTE_DIR}/${db}' \
        '${REMOTE_DIR}/${BACKUP_SUBDIR}/${db}' 2>/dev/null || true"
done

# ── push and verify ──
echo "--- Pushing ---"
for db in "${DBS[@]}"; do
    local_path="${BUILD_DIR}/${db}"
    echo "  $db"
    scp "$local_path" "${HOST}:${REMOTE_DIR}/${db}"
    local_sum=$(sha256sum "$local_path" | cut -d' ' -f1)
    remote_sum=$(ssh "$HOST" "sha256sum '${REMOTE_DIR}/${db}'" | cut -d' ' -f1)
    if [[ "$local_sum" != "$remote_sum" ]]; then
        echo "Error: checksum mismatch for ${db} after upload!" >&2
        exit 1
    fi
    echo "    verified (sha256 ${local_sum:0:12}...)"
done

echo "=== Done: ${#DBS[@]} database(s) pushed and verified ==="
