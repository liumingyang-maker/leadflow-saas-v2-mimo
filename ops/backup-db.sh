#!/usr/bin/env bash
# LeadFlow SaaS V2 — Database Backup
# Usage: ./ops/backup-db.sh
set -Eeuo pipefail

COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE="/etc/leadflow/production.env"
BACKUP_DIR="/var/backups/leadflow"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/leadflow_${TIMESTAMP}.dump"

mkdir -p "$BACKUP_DIR"

echo "===== LeadFlow Database Backup ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"

# Run pg_dump inside db container
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" \
  exec -T db pg_dump -U leadflow -d leadflow -Fc > "$BACKUP_FILE"

# Verify backup is not empty
if [ ! -s "$BACKUP_FILE" ]; then
  echo "FAIL: Backup file is empty."
  rm -f "$BACKUP_FILE"
  exit 1
fi

# Secure permissions
chmod 600 "$BACKUP_FILE"

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "Backup saved: $BACKUP_FILE ($SIZE)"
echo "PASS"
