#!/usr/bin/env bash
# LeadFlow SaaS V2 — Production Rollback
# Usage: ./ops/rollback.sh <previous-release-tag>
# Example: ./ops/rollback.sh v1.0.0-alpha.1
set -Eeuo pipefail

REPO_DIR="/opt/leadflow-saas-v2"
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE="/etc/leadflow/production.env"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <previous-release-tag>"
  echo "Example: $0 v1.0.0-alpha.1"
  exit 1
fi

TAG="$1"

echo "===== LeadFlow Production Rollback ====="
echo "Target tag: ${TAG}"
echo ""

# 1. Verify tag exists
cd "$REPO_DIR"
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "FAIL: Tag $TAG not found."
  exit 1
fi

# 2. Warning about migrations
echo "WARNING: Database migrations are NOT automatically rolled back."
echo "If the current release included destructive migrations, you must"
echo "manually restore the database from backup before proceeding."
echo ""
echo "Backup location: /var/backups/leadflow/"
echo ""
read -p "Continue with rollback? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
  echo "Rollback cancelled."
  exit 0
fi

# 3. Checkout previous tag
echo ""
echo "Checking out $TAG..."
git checkout "$TAG"

# 4. Build
echo ""
echo "===== Building images ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

# 5. Restart services
echo ""
echo "===== Restarting services ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d db redis
sleep 5
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d web worker

# 6. Healthcheck
echo ""
echo "===== Running healthcheck ====="
sleep 10
bash ops/healthcheck.sh

echo ""
echo "===== Rollback complete ====="
echo "Tag: $TAG"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "REMINDER: If migrations were destructive, restore from:"
echo "/var/backups/leadflow/"
