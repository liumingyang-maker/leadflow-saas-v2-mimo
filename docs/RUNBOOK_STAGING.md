# Runbook: Staging Setup

## Prerequisites

- Docker & Docker Compose
- Python 3.12+
- Git

## Start staging environment

```bash
docker compose up -d
docker compose ps
```

## Run migrations

```bash
docker compose run --rm web alembic upgrade head
```

## Verify

```bash
curl http://localhost:5000/health/live
curl http://localhost:5000/health/ready
```

## Worker

```bash
docker compose up -d worker
docker compose logs -f worker
```

## Environment

Set in `.env` or docker-compose environment:

```text
APP_ENV=staging
SECRET_KEY=<staging-secret>
TENANT_SECRET_KEY=<tenant-secret>
REDIS_URL=redis://redis:6379/0
DATABASE_URL=sqlite:///data/leadflow-v2.db
```

## Rollback

```bash
docker compose down
git checkout <previous-tag>
docker compose up -d
alembic downgrade -1
```

## Health endpoints

- `/health/live` — lightweight aliveness
- `/health/ready` — DB + Redis checks
