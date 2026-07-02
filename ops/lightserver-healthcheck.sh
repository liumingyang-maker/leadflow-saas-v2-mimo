#!/usr/bin/env bash
# LeadFlow SaaS V2 — Low-Memory Healthcheck
# Usage: bash ops/lightserver-healthcheck.sh
#
# Checks Redis, systemd services, and HTTP health endpoints.
set -Eeuo pipefail

BASE_URL="http://127.0.0.1:8000"
HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-huokeradar.com}"
WEB_SERVICE="leadflow-saas-v2-web.service"
WORKER_SERVICE="leadflow-saas-v2-worker.service"

echo "===== LeadFlow Low-Memory Healthcheck ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

FAILURES=0

# 1. Redis
echo -n "  Redis 127.0.0.1:6379 ... "
if ss -lntp 2>/dev/null | grep -q ':6379 '; then
  echo "PASS"
else
  echo "FAIL"
  FAILURES=$((FAILURES + 1))
fi

# 2. Web service
echo -n "  ${WEB_SERVICE} ... "
if systemctl is-active "$WEB_SERVICE" >/dev/null 2>&1; then
  echo "PASS"
else
  echo "FAIL"
  FAILURES=$((FAILURES + 1))
fi

# 3. Worker service
echo -n "  ${WORKER_SERVICE} ... "
if systemctl is-active "$WORKER_SERVICE" >/dev/null 2>&1; then
  echo "PASS"
else
  echo "FAIL"
  FAILURES=$((FAILURES + 1))
fi

# 4. Health live
echo -n "  /health/live ... "
if curl -fsS -H "Host: ${HEALTHCHECK_HOST}" "${BASE_URL}/health/live" >/dev/null 2>&1; then
  echo "PASS"
else
  echo "FAIL"
  FAILURES=$((FAILURES + 1))
fi

# 5. Health ready
echo -n "  /health/ready ... "
READY=$(curl -fsS -H "Host: ${HEALTHCHECK_HOST}" "${BASE_URL}/health/ready" 2>/dev/null || echo '{"ok":false}')
if echo "$READY" | grep -q '"ok":true'; then
  echo "PASS"
else
  echo "FAIL: $READY"
  FAILURES=$((FAILURES + 1))
fi

echo ""
if [ "$FAILURES" -eq 0 ]; then
  echo "RESULT: PASS"
  exit 0
else
  echo "RESULT: FAIL (${FAILURES} failures)"
  exit 1
fi
