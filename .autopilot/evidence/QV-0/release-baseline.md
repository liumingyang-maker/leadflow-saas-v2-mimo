# QV-0 Release Baseline Evidence

## Baseline

- Active branch: `design/solo-ai-acquisition-system`.
- Local HEAD before this documentation commit: `67b90ad001a4dde14af09d4fd9cc8e5795fce962`.
- Baseline design commit: `3d4d4cde3ebbaf82c4851b0167e691c2aec2d599`.
- Worktree: isolated.
- Migration current/head: `0021_radar_baseline_acceptance`.
- Only preserved user change: V2-05 screenshot.
- Static style repair commit `67b90ad001a4dde14af09d4fd9cc8e5795fce962` is mechanical Ruff-only and independently reviewed.

## Automated gates

- `pytest tests/acquisition -q`: exit 0 (69.1s).
- `pytest tests/radar tests/browser tests/test_migration_paths.py tests/test_worker_contracts.py tests/test_queue_safety.py -q`: exit 0 (28s).
- Current Ruff check: exit 0.
- Current Ruff format check: exit 0.
- `git diff --check`: exit 0.
- Disposable SQLite migration at `C:\\tmp\\leadflow-qv0-migration-20260804`: upgrade/current exit 0; head `0021_radar_baseline_acceptance`.

## Controlled runtime

- Docker configuration: exit 0; services: `db`, `redis`, `reconciler`, `web`, `worker`, `browser-egress`, `browser-redis`, `browser-worker`.
- `http://127.0.0.1:5000/health/ready`: HTTP 200; `{"checks":{"database":"ok","redis":"ok"},"ok":true}`.
- One Worker process tree: root `17752` -> child `21664`; source: `run_worker.py:57 worker.work(with_scheduler=True)`.
- Provider, browser, CRM, and outreach actions initiated by QV-0: 0.

## Scope audit

- QV-0 made no application behavior changes.
- Historical Phase 2 plan checkboxes are preserved.
- QV-1 starts only from the published QV-0 commit.

## Publication

- Branch: `design/solo-ai-acquisition-system`.
- Verified code-baseline local SHA: `c9b674a547e85e725260c591379c7ee127267e79`.
- Verified code-baseline remote SHA: `c9b674a547e85e725260c591379c7ee127267e79`.
- Published at (UTC): `2026-08-04T04:30:59Z`.
- This evidence file cannot record its own successor commit SHA; verify the current remote ref independently with `git ls-remote --heads origin design/solo-ai-acquisition-system`.
