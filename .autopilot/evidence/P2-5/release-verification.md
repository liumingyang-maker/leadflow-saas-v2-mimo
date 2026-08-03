# P2-5 release verification - 2026-08-03

## Fresh local checks

- python -m pytest -q -k "not browser" - exit 0; 100% passed; 142.3 seconds after the final lifecycle fixes.
- Focused Phase 2 tests - exit 0: deterministic Diff, manual Radar Jobs, Radar routes and signal decisions, relationships, Radar Candidate boundary, worker cancellation and recovery, and workbench projection.
- Disposable SQLite migration roundtrip - upgrade head -> downgrade 0020_radar_active_run_guard -> upgrade head; active_key=True and baseline_accepted=True.
- python -m alembic heads - 0021_radar_baseline_acceptance (head).
- Scoped Ruff for all touched Radar modules/tests and migrations 0018/0020/0021 - exit 0; all files formatted.
- git diff --check - exit 0.

## Docker runtime isolation

Previously executed scripts/smoke_browser_runtime.ps1 using Docker Desktop Engine 29.6.2 / Compose 5.3.1. This business-logic remediation did not modify the Browser image, worker, proxy, or transport contract.

- Browser worker image build: pass.
- Worker isolated environment: pass.
- Exact restricted MCP tool contract: pass.
- Runtime isolation smoke: pass.
- Browser worker, egress and transport Redis were stopped by the smoke script after validation.

## Full-repository formatting note

python -m ruff check . reports unrelated existing format/import findings in migrations/env.py, migration 0016, app/config.py, and untracked work/run_full_pytest.py. The only P2-owned formatting finding in migration 0018 was corrected; scoped checks are clean. No unrelated files were reformatted.

## Release blockers retained intentionally

- The 50+ labeled relationship/material-change corpus and its replay metrics have not been supplied; no precision percentage is claimed.
- No customer/staging website Run was performed.
- COMPETITOR_RADAR_ENABLED remains disabled by default and requires explicit operator approval before enablement.
