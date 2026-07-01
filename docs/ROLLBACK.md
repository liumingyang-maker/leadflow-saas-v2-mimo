# Rollback Guide

## When to Rollback

Rollback if:
- Critical bugs affect core user flows (registration, login, CRM, outreach)
- Data corruption detected
- SMTP delivery completely broken
- Security vulnerability discovered
- Performance degradation affecting users

Do NOT rollback for:
- Minor UI issues
- Non-critical feature bugs
- Issues in unvalidated features (AI, provider)

## Automated Rollback

```bash
cd /opt/leadflow-saas-v2
bash ops/rollback.sh <previous-tag>
```

Example:
```bash
bash ops/rollback.sh v1.0.0-alpha.1
```

## Manual Rollback

If the automated script fails:

### 1. Stop Services

```bash
cd /opt/leadflow-saas-v2
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env down
```

### 2. Checkout Previous Version

```bash
git checkout <previous-tag>
```

### 3. Rebuild and Start

```bash
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env build
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env up -d db redis
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env run --rm migrate
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env up -d web worker
```

### 4. Verify

```bash
bash ops/healthcheck.sh
```

## Database Rollback

**Warning**: Database migrations are NOT automatically rolled back.

If the release included destructive migrations (dropping columns, tables, or changing data types), you must restore from backup:

### 1. List Backups

```bash
ls -la /var/backups/leadflow/
```

### 2. Stop Services

```bash
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env down
```

### 3. Restore Database

```bash
# Start only db
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env up -d db
sleep 5

# Drop and recreate
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db dropdb -U leadflow leadflow
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db createdb -U leadflow leadflow

# Restore from backup
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db pg_restore -U leadflow -d leadflow < /var/backups/leadflow/leadflow_<timestamp>.dump
```

### 4. Start Services

```bash
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env up -d
bash ops/healthcheck.sh
```

## Backup Location

All backups are stored at `/var/backups/leadflow/` with timestamps:
- `leadflow_20260701_120000.dump`
- `leadflow_20260701_180000.dump`

Backups are created automatically before each deployment by `ops/deploy.sh`.

## Post-Rollback Checklist

- [ ] Healthcheck passes
- [ ] Registration works
- [ ] Login works
- [ ] SMTP works
- [ ] No data loss confirmed
- [ ] Incident documented
- [ ] Root cause analysis scheduled
