# Release Process

## Overview

This document describes the release process for LeadFlow SaaS V2.

## Release Steps

### 1. Complete RC Validation

- All RC items must pass (see `.autopilot/evidence/RC_VALIDATION_*.md`)
- RC-009 (SMTP) must pass with real email
- Go/No-Go must be GO

### 2. Create Release Tag

```bash
git tag -a v1.0.0-beta.1 -m "Release v1.0.0-beta.1 controlled paid beta"
git push origin v1.0.0-beta.1
```

### 3. Deploy to Production

```bash
cd /opt/leadflow-saas-v2
bash ops/deploy.sh v1.0.0-beta.1
```

### 4. Post-Deploy Verification

```bash
bash ops/healthcheck.sh
```

### 5. Monitor

- Check application logs for errors
- Monitor SMTP delivery and bounce rates
- Watch for user-reported issues

## Rollback Procedure

If issues are found after deployment:

```bash
bash ops/rollback.sh <previous-tag>
```

**Warning**: Database migrations are NOT automatically rolled back. If the release included destructive migrations, restore from backup:

```bash
# List backups
ls -la /var/backups/leadflow/

# Restore (manual process)
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db dropdb -U leadflow leadflow
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db createdb -U leadflow leadflow
docker compose -f docker-compose.production.yml --env-file /etc/leadflow/production.env exec -T db pg_restore -U leadflow -d leadflow < /var/backups/leadflow/leadflow_<timestamp>.dump
```

## Version Naming

- `v1.0.0-beta.1` — First controlled paid beta
- `v1.0.0-rc.1` — Release candidate
- `v1.0.0` — Stable release

## What NOT to Do

- Do not deploy without completing RC validation
- Do not push directly to production without a tag
- Do not skip the backup step
- Do not expose unvalidated provider features (AI, Google Search, Maps)
- Do not commit secrets to git
