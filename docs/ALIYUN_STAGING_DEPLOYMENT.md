# Aliyun Staging Deployment Runbook

This is a staging preparation guide. Do not deploy production or connect real customer data without explicit user approval.

## Recommended Server

- OS: Ubuntu 22.04 LTS or 24.04 LTS.
- Size: start with 2 vCPU, 4 GB RAM, 40 GB SSD.
- Runtime: Docker Engine plus Docker Compose plugin.
- Network: expose only 80, 443, and restricted SSH.
- Redis and database must not be exposed to the public internet.
- Use a dedicated staging instance, not a production server.

## Domain and TLS

1. Create a staging subdomain, for example `staging.yourdomain.com`.
2. Add a DNS A record pointing to the Aliyun ECS public IP.
3. Put Caddy or Nginx in front of the Flask web container.
4. Enable HTTPS with Caddy automatic TLS or Nginx plus Certbot.
5. Redirect HTTP to HTTPS.
6. Set `SESSION_COOKIE_SECURE=True` once HTTPS is active.

## Environment Variables

Use an `.env` file on the server or Aliyun secret management. Do not commit real values.

```text
FLASK_ENV=production
APP_ENV=production
SECRET_KEY=<generate-32-plus-character-random-value>
TENANT_SECRET_KEY=<generate-32-plus-character-random-value>
DATABASE_URL=<staging-database-url>
REDIS_URL=redis://redis:6379/0
SERVER_NAME=staging.yourdomain.com
ALLOWED_HOSTS=staging.yourdomain.com
WTF_CSRF_ENABLED=True
SESSION_COOKIE_SECURE=True
PROXY_FIX_HOPS=1
MAIL_PROVIDER=fake
GOOGLE_SEARCH_PROVIDER=fake
GOOGLE_MAPS_PROVIDER=fake
```

## Initial Deployment

```bash
git clone https://github.com/liumingyang-maker/leadflow-saas-v2.git
cd leadflow-saas-v2
git fetch --tags
git checkout v1.0.0-rc1
cp .env.example .env  # if available; otherwise create .env from the list above
docker compose pull || true
docker compose build
docker compose run --rm web python -m alembic upgrade head
docker compose up -d web worker redis db
docker compose ps
```

If using an external managed database, update `DATABASE_URL`, run migrations against that database, and remove/ignore the local SQLite placeholder service.

## Admin Creation

Use the project's admin creation service or a one-off Flask shell command after secrets and database are configured. Use a unique staging admin email and a strong temporary password. Force password rotation operationally before sharing the environment.

## Smoke Test

1. Visit `/health/live` and `/health/ready`.
2. Log in as admin and open `/admin/system`.
3. Register or seed a tenant account.
4. Log in as tenant and open `/settings`.
5. Open CRM list and lead detail drawer.
6. Run a fake collection job and verify job state survives page refresh.
7. Send a fake outreach email and verify no real mail is sent.
8. Generate an inbound token, add an allowed origin, and submit a test inbound lead.
9. Open tenant `/audit` and admin `/admin/audit`.
10. Restart worker and verify stale-job recovery logs.
11. Perform a backup and restore rehearsal.

## Backup and Restore

- Before every migration, back up the database.
- For SQLite staging, copy `/data/leadflow-v2.db` while containers are stopped or use a consistent snapshot.
- For PostgreSQL staging, use `pg_dump` and verify restore with `psql`.
- Redis is not the source of truth; jobs are persisted in SQL and recovered by the worker.

## Rollback

```bash
docker compose down
git checkout <previous-tag>
docker compose run --rm web python -m alembic downgrade -1
docker compose up -d web worker redis db
docker compose logs --no-color web --tail=100
docker compose logs --no-color worker --tail=100
```

Only downgrade one migration at a time after confirming backup availability.

## Third-Party Services

Keep providers in fake/mock mode for RC1 staging unless the user explicitly supplies credentials:

- Mail provider: fake.
- Google Search provider: fake.
- Google Maps provider: fake.
- Payments: not configured.

## Stop Conditions

Stop and ask the user before:

- Connecting real mail, Google, Maps, payment, DNS automation, or customer data.
- Opening staging to external users.
- Promoting staging to production.
