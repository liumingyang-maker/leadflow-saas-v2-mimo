# Runbook: Backup & Restore

## Database

**Source of truth:** LeadFlow uses SQLAlchemy with SQLite (dev) or PostgreSQL (prod).

### Backup

```bash
# SQLite
cp /data/leadflow-v2.db /data/backups/leadflow-$(date +%Y%m%d-%H%M).db

# PostgreSQL
pg_dump -h $DB_HOST -U $DB_USER leadflow > /data/backups/leadflow-$(date +%Y%m%d-%H%M).sql
```

### Restore

```bash
# SQLite
cp /data/backups/leadflow-20260101-120000.db /data/leadflow-v2.db

# PostgreSQL
psql -h $DB_HOST -U $DB_USER leadflow < /data/backups/leadflow-20260101-120000.sql
```

### Run migration after restore

```bash
cd /app && alembic upgrade head
```

## Redis

Redis is transient — not a source of truth. Jobs are persisted in SQL.
If Redis data is lost, run `python run_worker.py` to recover stale jobs.

## Migration safety

- Always backup before running `alembic upgrade head`
- Test downgrade before production: `alembic downgrade -1 && alembic upgrade head`
- Never skip version check

## Secret rotation

- `SECRET_KEY`, `TENANT_SECRET_KEY`, `INBOUND_TOKEN_KEY` must be rotated separately
- After rotation, restart all workers
- Inbound tokens must be regenerated via the UI after key rotation
