# Production Readiness Checklist

RC1 is ready for staging rehearsal, not production launch. Complete every item before production.

## Code and Tests

- [ ] Release tag checked out and verified.
- [ ] `python -m pytest` passes.
- [ ] Ruff check passes.
- [ ] Ruff format check passes.
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
- [ ] HTTPS is enforced.
- [ ] Host allowlist or proxy host validation is configured.
- [ ] Debug mode disabled.
- [ ] Error pages do not expose tracebacks.
- [ ] Tenant isolation tests pass.
- [ ] Admin routes require admin session.
- [ ] Audit logs store safe summaries and hashed request metadata only.
- [ ] The selected reverse proxy and WSGI access logger redact the path segment after `/verify-email/` and `/reset-password/`, verified against their actual emitted log lines.
- [ ] Hosted logging review confirms `safe_event` protects structured application events only and is not treated as access-log sanitization.
- [ ] Static fetching runs in an isolated Worker with network-layer private-range and metadata egress denial verified in the hosted environment.
- [ ] StaticFetcher DNS/connect TOCTOU residual risk is accepted only with the hosted network control above; local unit tests are not used as proof of closure.

## Operations

- [ ] Database backup schedule configured.
- [ ] Restore rehearsal completed.
- [ ] Migration rollback plan tested.
- [ ] Redis persistence expectations documented.
- [ ] Worker recovery tested after restart.
- [ ] SQLite deployment is limited to exactly one RQ Worker.
- [ ] PostgreSQL migration, concurrent promotion and multi-Worker smoke pass before Worker scale-out.
- [ ] Logs are collected without secrets.
- [ ] Health checks monitored.
- [ ] Alerting configured for web, worker, database, and Redis.

## Third-Party Providers

- [ ] Mail provider selected and credentials stored securely.
- [ ] Google Search provider selected and credentials stored securely.
- [ ] Google Maps provider selected and credentials stored securely.
- [ ] Provider rate limits documented.
- [ ] Provider failure behavior tested.
- [ ] No fake provider is enabled in production unless explicitly accepted.

## Manual Acceptance

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

- [ ] User explicitly approves production deployment.
- [ ] DNS cutover plan approved.
- [ ] Rollback owner assigned.
- [ ] Database backup verified immediately before deployment.
- [ ] Production secrets loaded from secure storage.
- [ ] No real customer data touched during rehearsal.
