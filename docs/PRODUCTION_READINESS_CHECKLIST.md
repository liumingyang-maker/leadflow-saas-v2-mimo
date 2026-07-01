# Production Readiness Checklist

RC1 is ready for staging rehearsal, not production launch. Complete every item before production.
Use `.autopilot/evidence/templates/production-readiness-evidence-template.md` for release evidence.
Unchecked items are not complete and must not be treated as PASS without attached evidence.

## Code and Tests

- [ ] Production readiness evidence template copied for this release candidate.
- [ ] Release candidate name, commit hash, branch, reviewer, date, and environment recorded.
- [ ] Staging config validated.
- [ ] Release tag checked out and verified.
- [ ] `python -m pytest` passes.
- [ ] Ruff check passes.
- [ ] Ruff format check passes.
- [ ] Docker build verified.
- [ ] Staging compose smoke passed.
- [ ] Migrations applied.
- [ ] Alembic `upgrade head -> downgrade -1 -> upgrade head` passes on staging-like data.
- [ ] All Playwright acceptance tests pass against staging.
- [ ] No unsafe rendering in runtime code.
- [ ] No remote runtime CDN dependency.
- [ ] No Alpine runtime dependency unless explicitly reintroduced and audited.

## Security

- [ ] `APP_ENV=production`.
- [ ] Strong `SECRET_KEY` generated and stored outside Git.
- [ ] Strong `TENANT_SECRET_KEY` generated and stored outside Git.
- [ ] `WTF_CSRF_ENABLED=True`.
- [ ] `SESSION_COOKIE_SECURE=True`.
- [ ] `PROXY_FIX_HOPS` matches the real reverse proxy hop count.
- [ ] SMTP verified with a real provider or explicitly accepted fake provider.
- [ ] Redis verified by `/health/ready`.
- [ ] PostgreSQL verified by migrations and `/health/ready`.
- [ ] HTTPS is enforced.
- [ ] Host allowlist or proxy host validation is configured.
- [ ] Debug mode disabled.
- [ ] Error pages do not expose tracebacks.
- [ ] Tenant isolation tests pass.
- [ ] Admin routes require admin session.
- [ ] Auth flows verified.
- [ ] Inbound/outreach security verified.
- [ ] Audit logs store safe summaries and hashed request metadata only.

## Operations

- [ ] Database backup schedule configured.
- [ ] Staging backup/restore smoke passed with `scripts/staging_backup_restore_smoke.py`.
- [ ] Restore rehearsal completed.
- [ ] Migration rollback plan tested.
- [ ] Staging migration rollback smoke passed with `scripts/staging_migration_rollback_smoke.py`.
- [ ] `/health/live` passed against staging.
- [ ] `/health/ready` passed against staging.
- [ ] Redis persistence expectations documented.
- [ ] Worker recovery tested after restart.
- [ ] Logs are collected without secrets.
- [ ] Health checks monitored.
- [ ] Alerting configured for web, worker, database, and Redis.

## Third-Party Providers

- [ ] Mail provider selected and credentials stored securely.
- [ ] Real SMTP verification recorded in release evidence.
- [ ] Google Search provider selected and credentials stored securely.
- [ ] Google Maps provider selected and credentials stored securely.
- [ ] Real provider verification recorded if real providers are enabled.
- [ ] Provider rate limits documented.
- [ ] Provider failure behavior tested.
- [ ] No fake provider is enabled in production unless explicitly accepted.

## Manual Acceptance

- [ ] Browser acceptance or manual acceptance completed.
- [ ] Login and logout.
- [ ] Onboarding.
- [ ] CRM list, import, drawer, stage change, note, tag, follow-up.
- [ ] Collection fake job and provider adapter boundary.
- [ ] Outreach fake send, tracking, unsubscribe.
- [ ] Inbound token generation, origin allowlist, API submission, idempotency.
- [ ] Admin dashboard and system diagnostics.
- [ ] Tenant and admin audit logs.
- [ ] Mobile layouts.
- [ ] Keyboard focus and Escape behavior where applicable.

## Production Go/No-Go

- [ ] Go/No-Go reviewed by owner.
- [ ] User explicitly approves production deployment.
- [ ] DNS cutover plan approved.
- [ ] Rollback owner assigned.
- [ ] Database backup verified immediately before deployment.
- [ ] Production secrets loaded from secure storage.
- [ ] No real customer data touched during rehearsal.
