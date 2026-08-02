# Runbook: Staging and Solo Deployment

## Supported Phase 1A shape

The default Compose stack is Web + Redis + SQLite + one `default` RQ Worker + one minute reconciler. This is intentionally sized for one operator. On Windows use Docker Desktop with the WSL2 backend; run Redis in Docker/WSL2 rather than as a native Windows service.

SQLite is not approved for multiple Workers. Move to PostgreSQL and pass the concurrency tests before scaling to two Workers. Do not claim PostgreSQL or real-provider validation from local SQLite tests.

## Configure and start

Supply secrets through a local `.env` or deployment secret store; never commit it.

```text
APP_ENV=production
SECRET_KEY=<at-least-32-random-characters>
TENANT_SECRET_KEY=<at-least-32-random-characters>
TRACKING_SIGNING_KEY=<at-least-32-random-characters>
UNSUBSCRIBE_SIGNING_KEY=<at-least-32-random-characters>
INBOUND_TOKEN_KEY=<at-least-32-random-characters>
REDIS_URL=redis://redis:6379/0
DATABASE_URL=sqlite:////data/leadflow-v2.db
MIMO_BASE_URL=<optional-provider-url>
```

When MiMo is enabled, inject `MIMO_API_KEY` through the deployment secret store rather than placing it in a committed file.

```bash
docker compose build
docker compose run --rm web alembic upgrade head
docker compose up -d
docker compose ps
curl --fail http://localhost:5000/health/live
curl --fail http://localhost:5000/health/ready
```

`live` is process-only. `ready` requires SQL and Redis, but deliberately does not require MiMo. Verify MiMo from Settings; manual URL research remains the provider-off fallback.

## Alerts and operator response

Application notifications are the default Phase 1A alert channel. Check the workbench at the start of the day and after a Mission is expected to finish.

| Signal | Threshold | First response |
|---|---:|---|
| Oldest queued Job | over 5 minutes | Check Worker logs and Redis, then run reconciler |
| Running Job heartbeat | older than 2 minutes | Let reconciler recover it; inspect safe error code |
| Failed Job rate | over 20% in 15 minutes | Pause new Missions and inspect provider/source failures |
| Disk usage | over 80% | Remove expired rotated logs/backups after confirming retention |
| Latest verified backup | older than 26 hours | Run backup immediately and verify non-zero artifact |
| MiMo consecutive failures | 3 | Use manual URL mode; check Settings before retrying |

Web, Worker and reconciler use Docker JSON log rotation of 10 MB with five files. Logs must never contain API keys, cookies, prompts, page bodies or URL query strings.

## Performance sampling

Capture a 15-minute window before changing Worker count. Keep the output with the release evidence and record the database type, MiMo model, sample size and Mission ID.

```bash
docker compose ps
docker compose logs --since=15m worker reconciler
docker stats --no-stream
docker system df
```

For the selected tenant, export only safe Job fields (`id`, `job_type`, `status`, `queued_at`, `started_at`, `finished_at`, `heartbeat_at`, `error_code`) and Mission cost summaries. Do not export payloads, page text, prompts, contacts or credentials. The provisional target for a 30-candidate Mission is 15 minutes to reviewable candidates; a manual URL should complete within 60 seconds. These are promotion gates to measure in PostgreSQL staging, not an SLA proven by local tests.

## Smoke test

1. Create/approve one product knowledge version.
2. Create a Mission using only product, country and buyer type; inspect Advanced only if needed.
3. With MiMo disabled, submit one public company URL and confirm Evidence plus deterministic Assessment are created.
4. Confirm an unknown country remains `needs_evidence` and cannot be accepted.
5. Accept one eligible Candidate and confirm exactly one tenant-scoped Lead.
6. Reject five candidates with the same reason; confirm a feedback suggestion appears but is not automatically applied.
7. Re-run reconciler and confirm terminal Mission notifications are not duplicated.

## PostgreSQL promotion gate

Before changing `DATABASE_URL` and Worker count, run migration upgrade/downgrade against a disposable PostgreSQL database, execute the full suite, then perform concurrent inbound idempotency and two-Worker queue tests. Start with two Workers only when the oldest queue repeatedly exceeds five minutes and the failure rate remains below 20%. Record timings and database version in the release evidence.

## Rollback

Take a backup, stop Worker and reconciler, deploy the previous image, and only downgrade a migration if its revision explicitly documents a safe downgrade. Restore the backup instead of forcing a destructive downgrade when data compatibility is uncertain.
