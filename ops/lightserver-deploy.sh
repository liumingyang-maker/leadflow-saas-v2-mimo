#!/usr/bin/env bash
# LeadFlow SaaS V2 — Low-Memory Light Server Deploy
# Usage: bash ops/lightserver-deploy.sh <release-tag>
# Example: bash ops/lightserver-deploy.sh v1.0.0-beta.2
#
# Target: Alibaba Cloud lightweight server (409 MiB RAM)
# Stack: Python 3.12 venv + gunicorn + SQLite + Redis (no Docker)
set -Eeuo pipefail

REPO_URL="https://github.com/liumingyang-maker/leadflow-saas-v2-mimo.git"
REPO_DIR="/opt/leadflow-saas-v2"
OLD_DIR="/opt/leadflow-v2"
BACKUP_DIR="/opt/leadflow-v2-backups"
VENV_DIR="${REPO_DIR}/.venv"
VAR_DIR="${REPO_DIR}/var"
PYTHON_BIN="/opt/leadflow-py312/bin/python"
ENV_FILE="/etc/leadflow/production.env"
HEALTHCHECK_SCRIPT="ops/lightserver-healthcheck.sh"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

if [ $# -lt 1 ]; then
  echo "Usage: $0 <release-tag>"
  echo "Example: $0 v1.0.0-beta.2"
  exit 1
fi

TAG="$1"
echo "===== LeadFlow Low-Memory Deploy ====="
echo "Tag: ${TAG}"
echo "Repo: ${REPO_DIR}"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ---------- Pre-flight checks ----------

echo "===== Pre-flight checks ====="

# Check Python 3.12
if [ ! -x "$PYTHON_BIN" ]; then
  echo "FAIL: Python 3.12 not found at ${PYTHON_BIN}"
  exit 1
fi
PY_VER=$("$PYTHON_BIN" --version 2>&1)
echo "  Python: ${PY_VER}"

# Check Redis
echo -n "  Redis 127.0.0.1:6379 ... "
if ss -lntp 2>/dev/null | grep -q ':6379 '; then
  echo "OK"
else
  echo "FAIL: Redis not listening on 127.0.0.1:6379"
  exit 1
fi

# Check git
if ! command -v git >/dev/null 2>&1; then
  echo "FAIL: git not installed."
  exit 1
fi
echo "  git: OK"

echo ""

# ---------- Backup old version ----------

echo "===== Backup old version ====="
mkdir -p "$BACKUP_DIR"

if [ -d "$OLD_DIR" ]; then
  BACKUP_NAME="leadflow-v2-backup-${TIMESTAMP}"
  echo "  Backing up ${OLD_DIR} -> ${BACKUP_DIR}/${BACKUP_NAME}"
  cp -a "$OLD_DIR" "${BACKUP_DIR}/${BACKUP_NAME}"
  echo "  Backup complete."
else
  echo "  No old version at ${OLD_DIR}, skipping."
fi

# Backup old SQLite if exists
OLD_DB="${OLD_DIR}/var/leadflow.sqlite3"
if [ -f "$OLD_DB" ]; then
  DB_BACKUP="${BACKUP_DIR}/leadflow-sqlite-${TIMESTAMP}.sqlite3"
  echo "  Backing up SQLite: ${DB_BACKUP}"
  cp "$OLD_DB" "$DB_BACKUP"
  chmod 600 "$DB_BACKUP"
fi

echo ""

# ---------- Clone or update repo ----------

echo "===== Clone / update repo ====="
if [ -d "${REPO_DIR}/.git" ]; then
  echo "  Repo exists, fetching..."
  cd "$REPO_DIR"
  git fetch --tags
else
  echo "  Cloning ${REPO_URL} ..."
  git clone "$REPO_URL" "$REPO_DIR"
  cd "$REPO_DIR"
fi

# Verify tag exists
if ! git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "FAIL: Tag ${TAG} not found."
  exit 1
fi

echo "  Checking out ${TAG}..."
git checkout "$TAG"
echo ""

# ---------- Virtual environment ----------

echo "===== Setup virtual environment ====="
if [ ! -d "$VENV_DIR" ]; then
  echo "  Creating venv..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "  Installing dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r requirements.txt -q
echo "  Dependencies installed."
echo ""

# ---------- Create var directory ----------

echo "===== Create var directory ====="
mkdir -p "$VAR_DIR"
echo "  ${VAR_DIR} ready."
echo ""

# ---------- Check production.env ----------

echo "===== Check production.env ====="
if [ -f "$ENV_FILE" ]; then
  echo "  ${ENV_FILE} exists."
else
  echo "  WARNING: ${ENV_FILE} not found."
  echo "  Create it before starting services. See docs/ALIYUN_LIGHTSERVER_DEPLOYMENT.md"
  echo "  Skipping migration and service start."
  echo ""
  echo "===== Deploy partially complete ====="
  echo "Tag: $TAG"
  echo "Next: create ${ENV_FILE}, then re-run this script."
  exit 0
fi

# ---------- Run migrations ----------

echo "===== Run migrations ====="
echo "  Running alembic upgrade head..."
cd "$REPO_DIR"
DATABASE_URL="sqlite:////opt/leadflow-saas-v2/var/leadflow.sqlite3" \
  "$VENV_DIR/bin/python" -m alembic upgrade head
echo "  Migrations complete."
echo ""

# ---------- Create systemd services ----------

echo "===== Create systemd services ====="

# Web service
cat > /etc/systemd/system/leadflow-saas-v2-web.service << EOF
[Unit]
Description=LeadFlow SaaS V2 Web (low-mem)
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/gunicorn -w 1 --threads 2 -b 127.0.0.1:8000 app:create_app()
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Worker service
cat > /etc/systemd/system/leadflow-saas-v2-worker.service << EOF
[Unit]
Description=LeadFlow SaaS V2 Worker (low-mem)
After=network.target redis.service

[Service]
Type=simple
User=root
WorkingDirectory=${REPO_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/python run_worker.py default
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
echo "  Systemd services created."
echo ""

# ---------- Start services ----------

echo "===== Start services ====="
systemctl start leadflow-saas-v2-web.service
systemctl start leadflow-saas-v2-worker.service

echo "  Waiting for services to stabilize..."
sleep 5

echo ""
echo "===== Service status ====="
systemctl is-active leadflow-saas-v2-web.service && echo "  web: active" || echo "  web: FAILED"
systemctl is-active leadflow-saas-v2-worker.service && echo "  worker: active" || echo "  worker: FAILED"
echo ""

# ---------- Healthcheck ----------

echo "===== Healthcheck ====="
if [ -f "$HEALTHCHECK_SCRIPT" ]; then
  bash "$HEALTHCHECK_SCRIPT" || true
else
  echo "  Healthcheck script not found, skipping."
fi

echo ""
echo "===== Deploy complete ====="
echo "Tag: $TAG"
echo "Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""
echo "NOTE: Apache ProxyPass is NOT modified."
echo "  Current: ProxyPass -> 127.0.0.1:8080 (old version)"
echo "  New version listens on: 127.0.0.1:8000"
echo "  Manually update Apache ProxyPass when ready to switch."
