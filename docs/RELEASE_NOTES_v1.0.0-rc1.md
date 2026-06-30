# LeadFlow SaaS V2 v1.0.0-rc1 Release Notes

## Status

`v1.0.0-rc1` is a release candidate for staging validation. It is not a production deployment.

- Functional baseline before release-prep docs: `952577aee93af7e92a012a588762944dbaa8e97a`
- Release-prep documentation commit: the commit containing these release notes; see the `v1.0.0-rc1` tag target.

## Included Milestones

- V2-01: Project governance, modular Flask foundation, data layer, design-system baseline, Docker baseline.
- V2-02: Accounts, tenants, onboarding, admin login, CSRF/cookie/proxy hardening, tenant secret encryption and rotation.
- V2-03: Leads, companies, tags, activities, import batches, CRM flows, lead detail drawer, tenant isolation, XSS/runtime closure.
- V2-04: Collection jobs, RQ/Redis worker bootstrap, fake search/maps adapters, durable job state, stale recovery.
- V2-05: Outreach, email templates, fake sending, tracking, suppression, unsubscribe, inbound API, origin allowlist, idempotency, rate limit.
- V2-06: Admin dashboard, audit log, settings, system diagnostics, safe error pages, launch runbooks, final browser acceptance.

## Verification Summary

- Full pytest: PASS, 273 tests collected.
- Ruff: PASS.
- Format: PASS.
- Alembic upgrade/downgrade/upgrade: PASS.
- Playwright CRM: PASS.
- Playwright Collection: PASS.
- Playwright Outreach/Inbound: PASS.
- Playwright Launch: PASS.
- Docker runtime: Not executed because Docker CLI is unavailable on this host.

## Security Summary

- Tenant-scoped repositories and service boundaries are covered by tests.
- Authenticated browser POST flows are CSRF protected.
- Production config rejects weak or missing `SECRET_KEY` and `TENANT_SECRET_KEY`.
- Secrets are encrypted at rest for tenant secret storage.
- Jobs persist tenant ownership and use JSON serialization.
- Runtime assets are local; no remote runtime CDN dependency is used.
- Unsafe rendering checks are covered by runtime closure tests.
- Real Google, Maps, mail, payment, DNS, and production data integrations were not accessed.

## Staging Notes

Use the Aliyun staging runbook in `docs/ALIYUN_STAGING_DEPLOYMENT.md`. Do not expose staging publicly until HTTPS, host allowlisting, secrets, backups, admin creation, and smoke tests are complete.

## Known Limitations

- Docker runtime validation still needs to be executed on a host with Docker.
- The included compose file is suitable as a local baseline; staging should use real secret injection and a reverse proxy.
- Real third-party providers remain mocked/fake until explicit credentials and provider decisions are supplied.
- This tag does not represent production readiness without the manual checklist in `docs/PRODUCTION_READINESS_CHECKLIST.md`.

## Safety

- Old repository modified: No.
- Real data modified: No.
- Business network accessed: No.
- Production deployed: No.
