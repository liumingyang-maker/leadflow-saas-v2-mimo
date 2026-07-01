#!/usr/bin/env bash
# LeadFlow SaaS V2 — Production Deploy
# Usage: ./ops/deploy.sh <release-tag>
# Example: ./ops/deploy.sh v1.0.0-beta.1
set -Eeuo pipefail

REPO_DIR="/opt/leadflow-saas-v2"
COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE="/etc/leadflow/production.env"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <release-tag>"
  echo "Example: $0 v1.0.0-beta.1"
  exit 1
fi

TAG="$1"

echo "===== LeadFlow Production Deploy ====="
echo "Tag: ${TAG}"
echo "Repo: ${REPO_DIR}"
echo ""

# 1. Check working tree
cd "$REPO_DIR"
if [ -n "$(git status --porcelain)" ]; then
  echo "FAIL: Working tree is not clean. Commit or stash changes first."
  git status --short
  exit 1
fi

# 2. Fetch tags
echo "Fetching tags..."
git fetch --tags

# 3. Verify tag exists
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "FAIL: Tag $TAG not found."
  exit 1
fi

echo "Checking out $TAG..."
git checkout "$TAG"

# 4. Pre-deploy backup
echo ""
echo "===== Pre-deploy backup ====="
bash ops/backup-db.sh

# 5. Build
echo ""
echo "===== Building images ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build

# 6. Start db and redis
echo ""
echo "===== Starting db and redis ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d db redis

# Wait for healthy
echo "Waiting for db and redis to be healthy..."
sleep 5

# 7. Run migrations
echo ""
echo "===== Running migrations ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm migrate

# 8. Start web and worker
echo ""
echo "===== Starting web and worker ====="
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d web worker

# 9. Healthcheck
echo ""
echo "===== Running healthcheck ====="
sleep 10
bash ops/healthcheck.sh

echo ""
echo "===== Deploy complete ====="
echo "Tag: $TAG"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
