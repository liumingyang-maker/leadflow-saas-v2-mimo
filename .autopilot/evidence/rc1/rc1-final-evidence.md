# LeadFlow SaaS V2 v1.0.0-rc1 Evidence

## Repository

- Repository: `C:/Users/97020/Desktop/leadflow-saas-v2`
- Initial release-prep baseline: `952577aee93af7e92a012a588762944dbaa8e97a`
- RC1 release-prep commit: the commit containing this evidence file; see final report/tag target.
- Branch at start: `main`
- Milestones completed and merged: V2-01, V2-02, V2-03, V2-04, V2-05, V2-06
- Production deployed: No

## Workspace Cleanup

- Restored V2-05 Playwright screenshot drift with precise `git restore -- .autopilot/evidence/V2-05/v2-05-outreach-desktop.png`.
- Kept `markdown/` as an untracked local draft directory. It was not deleted and is not part of RC1 evidence.
- No `git clean`, `git reset --hard`, force push, or old-repository write was used.

## Test Gates

- Python: `C:/Users/97020/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`
- Ruff: PASS
- Format: PASS, 106 files already formatted
- Full pytest: PASS
- Collected tests: 273
- Alembic: PASS, `upgrade head -> downgrade -1 -> upgrade head`
- `git diff --check`: PASS

## Playwright Gates

- `tests/test_playwright_crm.py`: PASS
- `tests/test_playwright_collection.py`: PASS
- `tests/test_playwright_outreach_inbound.py`: PASS
- `tests/test_playwright_launch_acceptance.py`: PASS
- Browser evidence already exists under `.autopilot/evidence/` for milestone flows.

## Security Grep Review

Raw grep output is saved in `.autopilot/evidence/rc1/security-grep.txt`.

- Unsafe rendering: no running app code uses `|safe`, `Markup`, or `render_template_string`.
- Remote CDN: no runtime template depends on remote CDN. `docs/THIRD_PARTY_ASSETS.md` records HTMX's upstream source URL while the app loads the local vendored asset.
- Alpine: no runtime Alpine attributes are present.
- Thread usage: only Playwright tests start local Werkzeug live-server threads.
- RQ pickle: no `pickle` hits; worker uses `rq.serializers.JSONSerializer`.
- Secret/password grep: hits are configuration key names, tests, docs, or password hashing/authentication code. No real production secret value was found or added.
- Real email providers: no SendGrid/Mailgun runtime integration; fake mailer remains the default dev/test boundary.

## Docker / Compose

- Docker runtime: Not executed. `docker` command is not available on this host.
- `docker compose config`: Not executed, Docker CLI unavailable.
- Container migration: Not executed, Docker CLI unavailable.
- Web/worker/redis/db container health: Not executed, Docker CLI unavailable.
- Static review:
  - `Dockerfile` uses `python:3.12-slim`, installs locked requirements when present, exposes `/health/live`, and starts Flask via the application factory.
  - `docker-compose.yml` defines `web`, `worker`, `redis`, and `db` services with pinned `redis:7.4.2-alpine` and `alpine:3.21.3` images.
  - `run_worker.py` runs stale-job recovery before worker start and uses `JSONSerializer`.
  - Compose is development-oriented and must be overridden for staging secrets and HTTPS/proxy settings.

## Release Documents

- Release notes: `docs/RELEASE_NOTES_v1.0.0-rc1.md`
- Aliyun staging runbook: `docs/ALIYUN_STAGING_DEPLOYMENT.md`
- Production readiness checklist: `docs/PRODUCTION_READINESS_CHECKLIST.md`
- Secrets/environment guide: `docs/SECRETS_AND_ENVIRONMENT.md`

## Known Limitations

- Docker runtime validation was not executed because Docker is not installed or not on PATH.
- Real Google, Maps, mail, payment, DNS, and SSH integrations were not accessed.
- Current compose file is a local/development compose baseline; Aliyun staging should use a staging env override and managed backup practice before external exposure.
- CSP is documented as a pre-production checklist item; current security headers are covered by existing middleware tests.

## Safety Confirmation

- Old repository modified: No
- Real data modified: No
- Business network accessed: No
- Production deployed: No
- Next action: Await user confirmation for Aliyun staging deployment
