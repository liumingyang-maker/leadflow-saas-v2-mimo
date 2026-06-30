# Runbook: Staging Setup

## Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Git

## Start staging environment

```bash
docker compose -f docker-compose.staging.yml up -d
docker compose -f docker-compose.staging.yml ps
```

## Run migrations

```bash
docker compose -f docker-compose.staging.yml run --rm web alembic upgrade head
```

## Verify

```bash
curl http://localhost:5000/health/live
curl http://localhost:5000/health/ready
```

## Worker

```bash
docker compose -f docker-compose.staging.yml up -d worker
docker compose -f docker-compose.staging.yml logs -f worker
```

## Environment

Set in `.env` or docker-compose environment:

```text
APP_ENV=staging
SECRET_KEY=<32-plus-character-staging-secret>
TENANT_SECRET_KEY=<32-plus-character-staging-secret>
POSTGRES_PASSWORD=<strong-postgres-password>
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql://leadflow:<postgres-password>@db:5432/leadflow
WTF_CSRF_ENABLED=true
SESSION_COOKIE_SECURE=true
PROXY_FIX_HOPS=1
SERVER_NAME=staging.example.com
ALLOWED_HOSTS=staging.example.com
INBOUND_TOKEN_KEY=<32-plus-character-staging-secret>
OUTREACH_SIGNING_KEY=<32-plus-character-staging-secret>
SMTP_HOST=<smtp-host>
SMTP_PORT=587
SMTP_USER=<smtp-user>
SMTP_PASSWORD=<smtp-password>
SMTP_FROM=<verified-from-address>
SMTP_USE_TLS=true
```

The compose file supplies `DATABASE_URL` and `REDIS_URL` to the web and worker
services. Do not use SQLite for staging. Account verification and password reset
emails require the SMTP variables above.

## Rollback

```bash
docker compose -f docker-compose.staging.yml down
git checkout <previous-tag>
docker compose -f docker-compose.staging.yml up -d
docker compose -f docker-compose.staging.yml run --rm web alembic downgrade -1
```

## Health endpoints

- `/health/live` — lightweight aliveness
- `/health/ready` — DB + Redis checks
