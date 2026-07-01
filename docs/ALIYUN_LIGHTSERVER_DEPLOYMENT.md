# Alibaba Cloud Lightweight Server Deployment Guide

**Target**: Alibaba Cloud Lightweight Application Server (409 MiB RAM, 20 GiB disk)
**Stack**: Python 3.12 + waitress + SQLite + Redis (no Docker)
**Domain**: huokeradar.com / www.huokeradar.com

> This is a **low-memory beta deployment**. It is NOT the final production architecture.
> For 2 GiB+ servers, use the Docker-based `ops/deploy.sh` instead.

## 1. Server Info

| Item | Value |
|---|---|
| Public IP | 8.218.122.200 |
| OS | Alibaba Cloud Linux (x86_64) |
| RAM | 409 MiB |
| Disk | 20 GiB |
| Python | 3.12 at `/opt/leadflow-py312/bin/python` |
| Web Server | Apache httpd (BT Panel) |
| Database | SQLite |
| Redis | 127.0.0.1:6379 |

## 2. Directory Layout

```
/opt/leadflow-saas-v2/          # New version (v1.0.0-beta.2+)
├── .venv/                      # Python 3.12 virtual environment
├── var/                        # SQLite database, logs
│   └── leadflow.sqlite3        # Production database
├── app/                        # Application code
├── ops/                        # Deployment scripts
└── ...

/opt/leadflow-v2/               # Old version (to be replaced)
/opt/leadflow-v2-backups/       # Backups
/opt/leadflow-py312/            # Python 3.12 installation

/etc/leadflow/production.env    # Production environment variables
```

## 3. Production Environment File

Create `/etc/leadflow/production.env`:

```bash
mkdir -p /etc/leadflow
cat > /etc/leadflow/production.env << 'ENVEOF'
# === App ===
APP_ENV=production
FLASK_APP=app:create_app
SECRET_KEY=<generate-32-char-secret>
TENANT_SECRET_KEY=<generate-32-char-secret>

# === Database (SQLite for low-mem) ===
DATABASE_URL=sqlite:////opt/leadflow-saas-v2/var/leadflow.sqlite3

# === Redis ===
REDIS_URL=redis://127.0.0.1:6379/0

# === Domain ===
SERVER_NAME=huokeradar.com
SITE_URL=https://huokeradar.com
ALLOWED_HOSTS=huokeradar.com,www.huokeradar.com,8.218.122.200,127.0.0.1,localhost

# === Security ===
WTF_CSRF_ENABLED=True
SESSION_COOKIE_SECURE=True
PROXY_FIX_HOPS=1

# === SMTP ===
MAIL_PROVIDER=smtp
SMTP_HOST=smtpdm.aliyun.com
SMTP_PORT=465
SMTP_USE_SSL=True
SMTP_USER=service@mail.huokeradar.com
SMTP_PASSWORD=<your-smtp-password>
MAIL_FROM=service@mail.huokeradar.com
MAIL_FROM_NAME=LeadFlow

# === Providers (disabled for beta) ===
GOOGLE_SEARCH_PROVIDER=fake
GOOGLE_MAPS_PROVIDER=fake

# === Signing keys (generate unique values) ===
INBOUND_TOKEN_KEY=<generate-32-char-secret>
OUTREACH_SIGNING_KEY=<generate-32-char-secret>
ENVEOF

chmod 600 /etc/leadflow/production.env
```

**Important**:
- `SMTP_PASSWORD` must NOT be committed to git.
- `SECRET_KEY`, `TENANT_SECRET_KEY`, `INBOUND_TOKEN_KEY`, `OUTREACH_SIGNING_KEY` must be unique random strings.
- Generate secrets with: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

## 4. Deploy

```bash
cd /opt/leadflow-saas-v2
bash ops/lightserver-deploy.sh v1.0.0-beta.2
```

This will:
1. Check Python 3.12 and Redis
2. Backup old version
3. Clone/update repo to specified tag
4. Create venv and install dependencies
5. Run Alembic migrations
6. Create systemd services
7. Start web (port 8000) and worker
8. Run healthcheck

## 5. Apache ProxyPass Switch

After deploy succeeds, switch Apache from old (8080) to new (8000):

```bash
# Edit Apache vhost config
vi /www/server/panel/vhost/apache/python_leadflow.conf

# Change:
#   ProxyPass / http://127.0.0.1:8080/
#   ProxyPassReverse / http://127.0.0.1:8080/
# To:
#   ProxyPass / http://127.0.0.1:8000/
#   ProxyPassReverse / http://127.0.0.1:8000/

# Restart Apache
systemctl restart httpd
```

## 6. Healthcheck

```bash
bash ops/lightserver-healthcheck.sh
```

Expected output:
```
RESULT: PASS
```

## 7. Rollback

If something goes wrong:

```bash
bash ops/lightserver-rollback.sh
```

Then restore Apache ProxyPass to 8080 and restart httpd.

## 8. Backup

```bash
bash ops/lightserver-backup-sqlite.sh
```

Backups are saved to `/opt/leadflow-v2-backups/`.

## 9. Firewall Rules

| Port | Service | Action |
|---|---|---|
| 22 | SSH | Keep, restrict source IP |
| 80 | HTTP | Keep |
| 443 | HTTPS | Keep |
| 8888 | BT Panel | Restrict source IP |
| 8000 | App (internal) | Do NOT expose |
| 6379 | Redis (internal) | Do NOT expose |
| 5432 | PostgreSQL (future) | Do NOT expose |

## 10. Limitations

- **SQLite**: Suitable for 1-3 beta users. Migrate to PostgreSQL for production.
- **No Docker**: Manual dependency management. Upgrade to Docker when RAM >= 2 GiB.
- **Single server**: All services on one machine. No horizontal scaling.
- **No auto-backup**: Run `lightserver-backup-sqlite.sh` manually or set up a cron job.

## 11. Future Migration Path

When upgrading to a 2 GiB+ server:
1. Install Docker + Docker Compose
2. Use `docker-compose.production.yml`
3. Migrate SQLite to PostgreSQL
4. Use `ops/deploy.sh` instead of `ops/lightserver-deploy.sh`
