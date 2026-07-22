# V2-04 Release Evidence

## Queue and Worker Safety

- RQ queues are constructed with `rq.serializers.JSONSerializer`.
- Enqueued function is fixed to `app.modules.jobs.worker.execute_job`.
- Redis payload contains only the fixed handler and server-generated `job_id`.
- Job payload, tenant ownership, and adapter inputs stay in SQL.
- Worker claims queued jobs with an atomic `UPDATE ... WHERE status = 'queued'`.
- Worker state writes re-fetch the job in an active SQLAlchemy session.
- Terminal jobs are refused by the worker claim path.
- Stale recovery uses rowcount-based compare-and-swap and does not rely on SELECT-then-blind-UPDATE.

## Runtime Versions

- Python: 3.12.13 in local bundled runtime.
- RQ: 2.9.1.
- redis-py: 8.0.0.
- Docker Redis image: `redis:7.4.2-alpine`.
- Docker helper DB image: `alpine:3.21.3`.
- Production Docker install path uses `requirements.lock`.

## Docker Validation

Docker CLI is not installed in this Windows host session:

```text
docker : The term 'docker' is not recognized as the name of a cmdlet, function, script file, or operable program.
```

Config-level repairs were applied:

- `Dockerfile` copies `run_worker.py`.
- `docker-compose.yml` includes `redis`, `db`, `web`, and `worker`.
- `redis` and `db` have health checks.
- `web` and `worker` wait for healthy runtime dependencies.

## Browser Evidence

- `v2-04-collection-desktop.png`
- `v2-04-collection-mobile.png`

Playwright collection smoke covers login, collection workspace, Google Search job flow, Google Maps job flow, screenshots, console errors, and local-only network hosts.

## Gate Results

- Targeted queue/worker/restart/job/milestone pytest: passed.
- Collection Playwright pytest: passed.
- Full pytest: passed.
- Ruff check: passed.
- Ruff format check: passed.
- Alembic upgrade -> downgrade -1 -> upgrade: passed.
- git diff --check: passed.

## Scope Notes

- CSV/XLSX remains routed through the existing V2-03 `/leads/import` server-side import flow. V2-04 collection workspace links to that flow and does not expose a second unsafe upload route.
- No production deployment was attempted.
- No real business network was accessed.
- Old repository was not modified.
