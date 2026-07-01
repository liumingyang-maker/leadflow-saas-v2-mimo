# Production Readiness Evidence Template

This is a template, not final release evidence. Do not mark a result `PASS`
unless the listed command or manual check actually ran and the output is attached
or referenced.

Allowed result values: `NOT_RUN`, `BLOCKED`, `PASS`, `FAIL`, `NEEDS_MANUAL_VERIFICATION`.

## Release Metadata

- Release candidate name / version: `NOT_RUN`
- Commit hash: `NOT_RUN`
- Branch: `NOT_RUN`
- Reviewer: `NOT_RUN`
- Date: `NOT_RUN`
- Environment: `NOT_RUN`
- Python version: `NOT_RUN`
- Docker version: `NOT_RUN`

## Automated Gates

| Check | Command or evidence source | Result | Evidence path / notes |
| --- | --- | --- | --- |
| Ruff result | `.venv/bin/ruff check .` | `NOT_RUN` | |
| Format check result | `.venv/bin/ruff format --check .` | `NOT_RUN` | |
| Pytest result | `PYTHONPATH=$PWD .venv/bin/python -m pytest -q` | `NOT_RUN` | |
| Browser / Playwright result | Playwright acceptance suite or staging browser run | `NOT_RUN` | |
| Docker build result | `docker compose -p <project> -f docker-compose.staging.yml build` | `NOT_RUN` | |
| Staging compose smoke result | `python scripts/staging_smoke.py --base-url <url>` | `NOT_RUN` | |
| Migration result | `docker compose -f docker-compose.staging.yml up migrate` | `NOT_RUN` | |
| Backup / restore smoke result | `python scripts/staging_backup_restore_smoke.py --confirm-staging` | `NOT_RUN` | |
| Migration rollback smoke result | `python scripts/staging_migration_rollback_smoke.py --confirm-staging` | `NOT_RUN` | |
| `/health/live` result | `curl -fsS <base-url>/health/live` | `NOT_RUN` | |
| `/health/ready` result | `curl -fsS <base-url>/health/ready` | `NOT_RUN` | |

## Manual / External Verification

| Check | Result | Evidence path / notes |
| --- | --- | --- |
| Real SMTP verification | `NEEDS_MANUAL_VERIFICATION` | |
| Real provider verification, if applicable | `NEEDS_MANUAL_VERIFICATION` | |
| Secrets loaded from approved storage | `NEEDS_MANUAL_VERIFICATION` | |
| Production host allowlist verified | `NEEDS_MANUAL_VERIFICATION` | |

## Limitations And Risks

- Known limitations: `NOT_RUN`
- Unresolved risks: `NOT_RUN`

## Go / No-Go

- Go / No-Go decision: `NOT_RUN`
- Approver: `NOT_RUN`
- Decision notes: `NOT_RUN`
