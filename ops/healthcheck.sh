#!/usr/bin/env bash
# LeadFlow SaaS V2 — Production Healthcheck
# Usage: ./ops/healthcheck.sh
set -Eeuo pipefail

COMPOSE_FILE="docker-compose.production.yml"
ENV_FILE="/etc/leadflow/production.env"
BASE_URL="http://127.0.0.1:8000"

echo "===== LeadFlow Healthcheck ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"

FAILURES=0

# 1. Health live
echo -n "  /health/live ... "
if curl -fsS "${BASE_URL}/health/live" >/dev/null 2>&1; then
  echo "PASS"
else
  echo "FAIL"
  FAILURES=$((FAILURES + 1))
fi

# 2. Health ready
echo -n "  /health/ready ... "
READY=$(curl -fsS "${BASE_URL}/health/ready" 2>/dev/null || echo '{"ok":false}')
if echo "$READY" | grep -q '"ok":true'; then
  echo "PASS"
else
  echo "FAIL: $READY"
  FAILURES=$((FAILURES + 1))
fi

# 3. Web container healthy
echo -n "  web container ... "
WEB_STATUS=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps web --format '{{.Status}}' 2>/dev/null || echo "unknown")
if echo "$WEB_STATUS" | grep -q "healthy"; then
  echo "PASS"
else
  echo "FAIL: $WEB_STATUS"
  FAILURES=$((FAILURES + 1))
fi

# 4. Worker container running
echo -n "  worker container ... "
WORKER_STATUS=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps worker --format '{{.Status}}' 2>/dev/null || echo "unknown")
if echo "$WORKER_STATUS" | grep -q "Up"; then
  echo "PASS"
else
  echo "FAIL: $WORKER_STATUS"
  FAILURES=$((FAILURES + 1))
fi

# 5. Migrate exited 0
echo -n "  migrate container ... "
MIGRATE_STATUS=$(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps migrate --format '{{.Status}}' 2>/dev/null || echo "unknown")
if echo "$MIGRATE_STATUS" | grep -q "Exited (0)"; then
  echo "PASS"
else
  echo "FAIL: $MIGRATE_STATUS"
  FAILURES=$((FAILURES + 1))
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "RESULT: PASS"
  exit 0
else
  echo "RESULT: FAIL ($FAILURES failures)"
  exit 1
fi
