# Phase 1A Remediation Gate Results

- Date: 2026-08-02
- Branch: `design/solo-ai-acquisition-system`
- Code HEAD tested: `df8007109a96e2105aada92db1d162c47765b1e9`
- Scope: local non-browser gates and a disposable SQLite migration round trip

## Executed gates

| Gate | Command | Result |
|---|---|---|
| Acquisition collection | `python -m pytest tests/acquisition --collect-only -q` | PASS — 288 collected |
| Acquisition suite | `python -m pytest tests/acquisition -q` | PASS — 288 passed, 0 failed |
| Ruff formatting | `python -m ruff format .` | PASS — 152 files left unchanged |
| Ruff lint | `python -m ruff check .` | PASS — `All checks passed!` |
| Ruff format verification | `python -m ruff format --check .` | PASS — 152 files already formatted |
| Non-browser collection | `python -m pytest --ignore=tests/test_playwright_launch_acceptance.py --ignore=tests/test_playwright_collection.py --ignore=tests/test_playwright_crm.py --ignore=tests/test_playwright_outreach_inbound.py --collect-only -q` | PASS — 580 collected |
| Complete non-browser suite | `python -m pytest --ignore=tests/test_playwright_launch_acceptance.py --ignore=tests/test_playwright_collection.py --ignore=tests/test_playwright_crm.py --ignore=tests/test_playwright_outreach_inbound.py -q` | PASS — 580 passed, 0 failed |
| Whitespace/error diff check | `git diff --check` | PASS — no output |

The plan's single-ignore pytest example was not used because repository inspection found four files that call `chromium.launch`. All four were explicitly excluded so this remained a non-browser gate.

## Disposable SQLite migration round trip

The database URL resolved to the direct worktree child:

`sqlite:///C:/Users/97020/Documents/Codex/2026-07-30/leadflow-saas-v2-codex-2026-07/work/worktrees/int-004-adr-foundation/.tmp-acq-remediation.db`

| Command | Result |
|---|---|
| `python -m alembic upgrade head` | PASS |
| `python -m alembic downgrade 0013_admin_auth_version` | PASS |
| `python -m alembic upgrade head` | PASS |
| `python -m alembic current` | PASS — `0014_acquisition_core (head)` |

Before cleanup, the resolved parent and exact `.tmp-acq-remediation.db` filename were validated for each explicit `.db`, `-wal`, and `-shm` removal. The disposable files were removed.

## Gates deliberately not run

| Gate | Status | Reason / required evidence |
|---|---|---|
| Browser / Playwright acceptance | NOT RUN | Browser execution was prohibited for this remediation gate. The four Playwright files were explicitly excluded. |
| Docker Compose runtime | NOT RUN | Requires Docker Desktop/WSL2 or a Linux Docker host and runtime evidence. |
| PostgreSQL migration and concurrency | NOT RUN | Requires disposable PostgreSQL plus concurrent promotion and multi-Worker smoke evidence. SQLite remains limited to one RQ Worker. |
| 30-company positive/negative sample | NOT RUN | Requires real sample precision, coverage, elapsed time, and provider-cost evidence. |
| Hosted access-log redaction | NOT RUN | The selected reverse proxy and WSGI logger must redact tokens after `/verify-email/` and `/reset-password/`, verified against emitted log lines. `safe_event` covers structured application events only. |
| Isolated fetcher egress enforcement | NOT RUN | The hosted fetcher Worker must have network-layer private-range/metadata egress denial to mitigate DNS/connect TOCTOU residual risk. |

## Safety statement

No real external fetch, MiMo paid API call, email send, browser automation, Docker runtime, or PostgreSQL service was used. Local unit tests do not close the hosted access-log, network-egress, PostgreSQL concurrency, Docker runtime, or real-sample gates.
