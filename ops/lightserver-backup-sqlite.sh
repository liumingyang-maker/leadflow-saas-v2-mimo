#!/usr/bin/env bash
# LeadFlow SaaS V2 — SQLite Backup (Low-Memory)
# Usage: bash ops/lightserver-backup-sqlite.sh
#
# Backs up SQLite databases from both old and new installations.
set -Eeuo pipefail

BACKUP_DIR="/opt/leadflow-v2-backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OLD_DB="/opt/leadflow-v2/var/leadflow.sqlite3"
NEW_DB="/opt/leadflow-saas-v2/var/leadflow.sqlite3"

echo "===== LeadFlow SQLite Backup ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

mkdir -p "$BACKUP_DIR"

FAILURES=0

# Backup old version SQLite
if [ -f "$OLD_DB" ]; then
  DEST="${BACKUP_DIR}/leadflow-v2-sqlite-${TIMESTAMP}.sqlite3"
  if cp "$OLD_DB" "$DEST"; then
    chmod 600 "$DEST"
    SIZE=$(du -h "$DEST" | cut -f1)
    echo "  Old DB backed up: ${DEST} (${SIZE})"
  else
    echo "  FAIL: Could not backup ${OLD_DB}"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "  Old DB not found: ${OLD_DB} (skipped)"
fi

# Backup new version SQLite
if [ -f "$NEW_DB" ]; then
  DEST="${BACKUP_DIR}/leadflow-saas-v2-sqlite-${TIMESTAMP}.sqlite3"
  if cp "$NEW_DB" "$DEST"; then
    chmod 600 "$DEST"
    SIZE=$(du -h "$DEST" | cut -f1)
    echo "  New DB backed up: ${DEST} (${SIZE})"
  else
    echo "  FAIL: Could not backup ${NEW_DB}"
    FAILURES=$((FAILURES + 1))
  fi
else
  echo "  New DB not found: ${NEW_DB} (skipped)"
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "RESULT: PASS"
  exit 0
else
  echo "RESULT: FAIL (${FAILURES} failures)"
  exit 1
fi
