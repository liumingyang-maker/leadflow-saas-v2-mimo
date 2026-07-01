#!/usr/bin/env bash
# LeadFlow SaaS V2 — Low-Memory Light Server Rollback
# Usage: bash ops/lightserver-rollback.sh
#
# Stops new services, reminds to restore Apache ProxyPass, restarts old services.
set -Eeuo pipefail

OLD_SERVICES="leadflow-v2-web.service leadflow-v2-worker.service"
NEW_SERVICES="leadflow-saas-v2-web.service leadflow-saas-v2-worker.service"

echo "===== LeadFlow Low-Memory Rollback ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# 1. Stop new services
echo "===== Stop new services ====="
for svc in $NEW_SERVICES; do
  if systemctl is-active "$svc" >/dev/null 2>&1; then
    systemctl stop "$svc"
    echo "  Stopped: $svc"
  else
    echo "  Already stopped: $svc"
  fi
done
echo ""

# 2. Apache ProxyPass reminder
echo "===== Apache ProxyPass Reminder ====="
echo "  Current new version listens on: 127.0.0.1:8000"
echo "  Old version listens on: 127.0.0.1:8080"
echo ""
echo "  ACTION REQUIRED: Restore Apache ProxyPass to 8080:"
echo "    Edit: /www/server/panel/vhost/apache/python_leadflow.conf"
echo "    Change: ProxyPass / http://127.0.0.1:8000/"
echo "    To:     ProxyPass / http://127.0.0.1:8080/"
echo "    Then: systemctl restart httpd"
echo ""

# 3. Start old services
echo "===== Start old services ====="
for svc in $OLD_SERVICES; do
  if systemctl is-enabled "$svc" >/dev/null 2>&1; then
    systemctl start "$svc"
    echo "  Started: $svc"
  else
    echo "  Service not found: $svc"
  fi
done
echo ""

# 4. Verify old services
echo "===== Verify old services ====="
for svc in $OLD_SERVICES; do
  STATUS=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
  echo "  ${svc}: ${STATUS}"
done

echo ""
echo "===== Rollback complete ====="
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "NOTE: New version files at /opt/leadflow-saas-v2 are NOT deleted."
echo "  You can re-deploy later or delete manually."
