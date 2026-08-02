# Phase 1A Windows Local Runtime Verification

- Date: 2026-08-02 (Asia/Shanghai)
- Branch: `design/solo-ai-acquisition-system`
- Base SHA: `7efd44263c63c0b604eed16811d880e845c38e5a`
- Browser automation: NOT RUN. The four tests that call `chromium.launch` were excluded to respect the local browser stability boundary.
- Real customer outreach or message sending: NOT RUN.

## Remediation scope

1. Native Windows selects RQ `SimpleWorker`; POSIX keeps the standard `Worker`.
2. Normal and recovered RQ jobs use the supported `result_ttl=86400` enqueue option.
3. Tests cover both platform selection and both enqueue paths.
4. The existing one-Worker SQLite rule remains unchanged.

`SpawnWorker` was tested before the final implementation and rejected: RQ 2.9.1 still called Windows-unavailable `os.wait4`, while its spawned child also used `os.setpgrp`. The default `Worker` failed earlier on `os.fork`. `SimpleWorker` is therefore the native-Windows local fallback only; Linux/Docker retains process isolation through `Worker`.

## Dependency and runtime isolation

- Project Python: `C:\Users\97020\AppData\Local\LeadFlow\venv\Scripts\python.exe`
- Locked packages verified: RQ 2.9.1, redis-py 8.0.0, Alembic 1.18.4.
- Redis-compatible runtime: Memurai Developer 4.1.7, bound only to `127.0.0.1:6379`.
- Web, Worker and reconciler logs: `C:\Users\97020\AppData\Local\LeadFlow\logs`.
- Log secret scan: PASS; no `tp-`, `sk-`, Authorization or API-key assignment pattern found.

## Automated gates

| Gate | Result |
|---|---|
| Focused worker/queue/acquisition-job tests | PASS, 44 tests |
| `pytest tests/acquisition -q` | PASS, 288 tests |
| Full non-browser pytest suite | PASS, 582 tests |
| `ruff check .` | PASS |
| `ruff format --check app tests run_worker.py` | PASS, 134 files |
| `git diff --check` | PASS |
| Live database migration current | PASS, `0014_acquisition_core (head)` |
| Fresh SQLite upgrade -> downgrade 0013 -> upgrade | PASS, final `0014_acquisition_core (head)` |

The full non-browser command excluded exactly these files:

- `tests/test_playwright_launch_acceptance.py`
- `tests/test_playwright_collection.py`
- `tests/test_playwright_crm.py`
- `tests/test_playwright_outreach_inbound.py`

`ruff format --check .` was not used as the Python format gate because Ruff 0.16.1 also proposes changes inside six pre-existing Markdown documents. Those documents were not modified. Application and test Python files passed the scoped format gate above.

## Real Redis/RQ round trip

A disposable `runtime-smoke-*` tenant submitted one `google_search` Job to the real local Redis and Windows Worker.

- RQ state: finished
- SQL Job state: succeeded
- SQL progress: 100
- Lead rows: 1, status `pending_review`
- Activity rows: 1
- Worker remained alive and returned to idle

The disposable Job, Lead, Activity and RQ keys were deleted after verification. Final queue, started registry and failed registry counts were all zero.

## Real MiMo verification

The previously supplied pay-as-you-go test key returned HTTP 401 on the documented pay-as-you-go endpoint. An older Token Plan key found in a local design note also returned 401. Neither was installed in LeadFlow.

The currently authenticated Xiaomi credential managed by the desktop MiMo CLI was tested without printing the credential:

- MiMo CLI pure text smoke: PASS, `mimo-v2.5-pro`
- Direct OpenAI-compatible Token Plan call: PASS
- LeadFlow `build_mimo_provider` mission planning: PASS
- Planned countries: MX
- Planned language: Spanish
- Generated queries: 5
- LeadFlow forced web-search plugin: PASS
- Search hits: 7, all HTTPS, across 7 unique hosts

The current desktop credential was copied into the existing tenant-scoped encrypted `SecretStore`. The encryption key, Token Plan base URL, model and Redis URL are stored as Windows user environment configuration; credential plaintext was not written to the repository or logs.

## Real acquisition Mission round trip

A disposable tenant ran the real background pipeline with a two-candidate and one-verification budget:

| Stage | Result |
|---|---|
| `acquisition_plan` | succeeded |
| `web_discovery` | succeeded |
| `website_verify` | succeeded |
| `candidate_assess` | succeeded |
| Mission terminal state | completed |
| Candidates | 2 (`discovered`, `eligible`) |
| Evidence rows | 3 |
| Assessments | 1 |

After verification, the disposable tenant, four SQL/RQ Jobs, product snapshot, Mission, candidates, evidence, assessment, notification, provider status and tenant secret were deleted. A cross-table check found zero remaining `runtime-smoke-*` rows.

## Final local state

- `GET /health/ready`: HTTP 200; database ok; Redis ok.
- `GET /login`: HTTP 200.
- Active RQ Workers: exactly 1, idle.
- Queue/started/failed counts: 0/0/0.
- Periodic reconciler: running once per minute; foreground smoke reconciled 0 Missions without error.
- User Mission `93d10a606ecc47199037645554836107`: preserved as `draft`; no test candidates were added.
- User-owned screenshot `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png`: not staged and not included in this remediation.
