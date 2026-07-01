# Low-Memory Beta Deployment

**Status**: Active for beta phase
**Applicability**: Servers with < 1 GiB RAM (e.g., Alibaba Cloud Lightweight 409 MiB)

## Why This Approach

The standard production deployment uses Docker + PostgreSQL + Nginx. That stack requires at least 1.5-2 GiB RAM. For lightweight servers, we use a stripped-down stack:

| Component | Standard | Low-Memory |
|---|---|---|
| Container | Docker | None (bare metal) |
| Database | PostgreSQL | SQLite |
| Web Server | Nginx | Apache (BT Panel) |
| App Server | Gunicorn | waitress |
| Worker | RQ in Docker | RQ bare metal |
| RAM Required | 2+ GiB | ~300 MiB |

## Architecture

```
Internet
  │
  ▼
Apache (BT Panel) :80/:443
  │ ProxyPass
  ▼
waitress :127.0.0.1:8000
  │
  ├── SQLite (/opt/leadflow-saas-v2/var/leadflow.sqlite3)
  └── Redis (127.0.0.1:6379)
        │
        ▼
   RQ Worker (run_worker.py)
```

## Scripts

| Script | Purpose |
|---|---|
| `ops/lightserver-deploy.sh` | Deploy a release tag |
| `ops/lightserver-rollback.sh` | Rollback to old version |
| `ops/lightserver-backup-sqlite.sh` | Backup SQLite databases |
| `ops/lightserver-healthcheck.sh` | Health check |

## Systemd Services

| Service | Description |
|---|---|
| `leadflow-saas-v2-web.service` | Web server (waitress on port 8000) |
| `leadflow-saas-v2-worker.service` | Background job worker (RQ) |

Check status:
```bash
systemctl status leadflow-saas-v2-web.service
systemctl status leadflow-saas-v2-worker.service
journalctl -u leadflow-saas-v2-web.service -f
```

## Environment Variables

All secrets live in `/etc/leadflow/production.env` (chmod 600). This file is:
- Loaded by systemd via `EnvironmentFile`
- Never committed to git
- Never printed in logs

Required variables:
- `SECRET_KEY` - Flask session secret
- `TENANT_SECRET_KEY` - Tenant isolation
- `DATABASE_URL` - SQLite path
- `REDIS_URL` - Redis connection
- `SMTP_PASSWORD` - Email sending
- `INBOUND_TOKEN_KEY` - Inbound webhook signing
- `OUTREACH_SIGNING_KEY` - Outreach signing

## SQLite Considerations

SQLite is used for low-memory deployment. Limitations:
- Single-writer (no concurrent writes)
- No network access (file-based)
- Suitable for 1-3 concurrent users
- Regular backups essential

Backup schedule recommendation:
```bash
# Daily backup via cron
0 2 * * * /opt/leadflow-saas-v2/ops/lightserver-backup-sqlite.sh
```

## Database Migrations

Alembic works with SQLite. Run migrations with:
```bash
cd /opt/leadflow-saas-v2
DATABASE_URL=sqlite:////opt/leadflow-saas-v2/var/leadflow.sqlite3 \
  .venv/bin/python -m alembic upgrade head
```

The deploy script handles this automatically.

## When to Upgrade

Migrate to Docker + PostgreSQL when:
- More than 3 concurrent users
- RAM upgraded to 2+ GiB
- Need for horizontal scaling
- Need for database network access

Migration steps:
1. Backup SQLite database
2. Set up PostgreSQL
3. Export SQLite data, import to PostgreSQL
4. Update `DATABASE_URL` in production.env
5. Switch to `ops/deploy.sh` (Docker-based)
6. Update Apache ProxyPass if needed

## Security Notes

- SSH access should be restricted by IP
- BT Panel (port 8888) should be restricted by IP
- Port 8000 (app) must NOT be exposed to internet
- Port 6379 (Redis) must NOT be exposed to internet
- All secrets in `/etc/leadflow/production.env` with chmod 600
