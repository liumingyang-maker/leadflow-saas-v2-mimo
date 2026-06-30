# V2-05 Release Evidence

## Outreach and Inbound - Implementation Summary

### Outreach
- `EmailTemplate`, `OutreachMessage`, `EmailTracking`, and `Suppression` are tenant-scoped.
- Fake mailer is used for development and tests; production/staging without a real provider returns `mailer_not_configured`.
- Suppression is checked before send.
- Tracking pixel records opens and always returns a cache-disabled 1x1 GIF.
- Click redirects are HMAC-signed, time-limited, and restricted to safe `http`/`https` public targets.
- Unsubscribe uses a signed public token: GET confirms, POST executes, and repeated POSTs are idempotent.
- Activity timeline actions are covered by the model and migration constraint.

### Inbound
- Tokens are generated with high entropy, looked up by SHA-256 digest, and stored encrypted.
- Origin allowlist requires full scheme, host, and optional port; wildcards, paths, and unsafe schemes are rejected.
- CORS preflight returns local allowlist headers with `Vary: Origin`.
- POST requires JSON, a valid token, allowed origin when `Origin` is present, DB-backed rate limit, body-size limit, and idempotency protection.
- Idempotency supports explicit keys and no-key payload fingerprint replay.
- Honeypot submissions return accepted without creating a lead.
- Lead creation is tenant-scoped, source=`inbound`, status=`pending_review`, and writes an activity event.

### Templates and UI
- `outreach/dashboard.html`: deliverability overview, template list, empty states.
- `outreach/templates.html`: authenticated template create/list.
- `outreach/lead_send.html`: compose form, suppression/error surface, sent history.
- `outreach/unsubscribe_confirm.html` and `outreach/unsubscribed.html`: public unsubscribe flow.
- `inbound/settings.html`: token management and allowed-origin management.

### Security Checks
- Authenticated browser POST routes have real CSRF coverage.
- Public unsubscribe POST is protected by signed token and idempotency, not session CSRF.
- Inbound API is intentionally CSRF-exempt and protected by token, origin allowlist, rate limit, idempotency, content type, and size limit.
- No `|safe`, `Markup`, `render_template_string`, remote runtime CDN, or Alpine runtime in non-test code.
- No real email provider integration or business network access.
- Secret/token plaintext is not persisted in templates beyond one-time inbound token display.

### Corrective Work by Codex
- Added the missing lead send and unsubscribe templates.
- Fixed outbound send error rendering so it preserves tenant-scoped lead, templates, and history.
- Fixed public unsubscribe lookup while keeping the signed-token boundary.
- Enforced inbound POST origin rejection before processing.
- Stored fingerprint idempotency entries for no-key inbound submissions.
- Normalized SQLite naive datetimes before rate-limit/idempotency comparisons.
- Stored inbound `company` and `message` in lead notes instead of passing a nonexistent `Lead.company` field.
- Updated `0009_outreach_inbound` to alter the Activity action constraint and support upgrade/downgrade smoke.
- Added focused Flask/security tests and a Playwright browser smoke with screenshots.

### Evidence Files
- `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png`
- `.autopilot/evidence/V2-05/v2-05-inbound-mobile.png`

### Gate Results
- `python -m pytest`: PASS, 267 tests
- `python -m pytest tests/test_outreach_inbound.py -q`: PASS, 5 tests
- `python -m pytest tests/test_playwright_outreach_inbound.py -q`: PASS, 1 test
- `python -m ruff check .`: PASS
- `python -m ruff format --check .`: PASS
- `python -m alembic upgrade head`: PASS
- `python -m alembic downgrade -1`: PASS
- `python -m alembic upgrade head`: PASS
- `git diff --check`: PASS

### Scope Compliance
- Old repository modified: No
- Real data modified: No
- Business network accessed: No
- Production deployed: No
