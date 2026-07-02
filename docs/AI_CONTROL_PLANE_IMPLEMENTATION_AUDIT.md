# AI Control Plane Implementation Audit

Date: 2026-07-02
Target: v1.1.0 AI Control Plane
Status: READY_FOR_MIMOCODE_REVIEW

Note: Codex sandbox cannot write to `/home/brian/Desktop` in this session. This report is written in-repo at `docs/AI_CONTROL_PLANE_IMPLEMENTATION_AUDIT.md`.

## Scope Completed

Implemented the v1.1.0 staged plan as one reviewable change set:

- v1.1.0-alpha.1: AI models, provider settings, disabled provider, fake provider, admin AI page.
- v1.1.0-alpha.2: tenant quota model, quota summary, AI usage ledger.
- v1.1.0-alpha.3: OpenAI-compatible provider, MiMo-ready configuration path, provider test connection.
- v1.1.0-alpha.4: outreach draft generation from the existing lead outreach page.
- v1.1.0-beta.1 preparation: fake provider and OpenAI-compatible provider are test-covered; real MiMo credentials were not used.

## Architecture Review

AI is implemented as an independent bounded context:

- Business-facing AI orchestration lives under `app/modules/ai/`.
- External model adapters live under `app/integrations/ai/`.
- Outreach routes call `app.modules.ai.service.generate_outreach_draft()` and do not instantiate model providers directly.
- OpenAI-compatible HTTP calls are isolated in `app/integrations/ai/openai_compatible.py`.
- No OpenAI SDK or new production dependency was added.

## Database Review

Migration added:

- `migrations/versions/0011_ai_control_plane.py`

Tables added:

- `ai_provider_settings`
- `tenant_ai_quotas`
- `ai_usage_ledger`

Review result:

- No prompt column.
- No response column.
- Ledger stores only summary metadata: tenant, user, feature, provider, model, credits, token counts, status, error code, latency, timestamp.
- SQLite beta is supported for low-concurrency use.
- Strong quota consistency under concurrency is intentionally deferred to PostgreSQL row-locking in a later release.

## Secret Review

Implemented shared secret crypto helper:

- `app/core/secret_crypto.py`

Existing tenant secret storage now reuses the shared helper:

- `app/modules/accounts/secret_store.py`

AI provider API keys:

- Stored encrypted in `ai_provider_settings.api_key_encrypted`.
- Last four characters stored separately in `api_key_last4`.
- Admin UI shows only a masked value such as `****1234`.
- Updating a key requires re-entering the full key.
- Tests use fake keys only.

No real API key, SMTP password, or production secret was added.

## Provider Review

Providers implemented:

- `DisabledProvider`
- `FakeAIProvider`
- `OpenAICompatibleProvider`

MiMo is supported through the OpenAI-compatible provider configuration:

- provider: `openai_compatible`
- base_url: MiMo-compatible API base URL
- model: MiMo model name
- api_key: stored encrypted

Provider errors are sanitized to stable error codes and short summaries. Provider calls use timeout-controlled standard-library HTTP.

## Quota / Ledger Review

Default monthly credits:

- trial: 100
- basic: 1000
- pro: 5000
- ultra: 5000

Outreach draft cost:

- 5 credits

Rules implemented:

- AI disabled: do not call provider, write `disabled` ledger, charge 0.
- Quota insufficient: do not call provider, write `blocked_quota` ledger, charge 0.
- Provider failure: write `failed` ledger, charge 0.
- Provider success: write `success` ledger, charge 5 credits.

## Admin UI Review

Added:

- `/admin/ai`

Page sections:

- Provider settings
- Test connection
- Usage summary
- Tenant quotas

This stays as one page for v1.1.0 and avoids premature `/provider`, `/quotas`, `/usage` route splitting.

## Tenant UI Review

Added:

- `/ai/quota` JSON endpoint for the authenticated tenant.
- AI quota summary on `/leads/<lead_id>/outreach`.

Tenant users can see:

- included credits
- used credits
- remaining credits
- draft cost

Tenant users cannot see:

- provider
- base_url
- API key
- other tenant usage

## Outreach Draft Review

Added:

- `POST /leads/<lead_id>/outreach/ai-draft`

Behavior:

- Checks AI enabled.
- Checks quota.
- Builds a minimal prompt from lead context.
- Calls the provider only through AI service.
- Fills subject/body draft into the existing compose form.
- Does not create `OutreachMessage`.
- Does not send email.
- Does not save full prompt or full generated response.

## Test Review

New tests:

- `tests/test_ai_control_plane.py`
- `tests/test_ai_outreach_draft.py`

Existing tests adjusted:

- Locale-sensitive tests now explicitly request `en-US` where they assert English copy.
- Static drawer semantic test now checks the translation call used by the single-template i18n system.

Validated:

- AI admin default disabled.
- Provider settings save.
- API key encryption and masked display.
- Fake provider test connection.
- Tenant quota endpoint.
- OpenAI-compatible request shape.
- Missing provider config fails safely.
- Outreach AI controls render.
- Fake draft generates Chinese and English drafts.
- Successful draft charges 5 credits.
- Disabled AI writes disabled ledger.
- Insufficient quota writes blocked ledger.
- AI draft does not send or create an outreach message.
- Translation key parity still passes.

## Commands Run

Passing:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
PYTHONPATH=$PWD .venv/bin/python -m pytest -q tests/test_i18n.py tests/test_auth*.py tests/test_password_reset.py tests/test_smtp_adapter.py tests/test_outreach_inbound.py tests/test_ai_control_plane.py tests/test_ai_outreach_draft.py
PYTHONPATH=$PWD .venv/bin/python -m pytest -q -k 'not playwright and not browser_acceptance'
git diff --check
```

Full pytest:

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest -q
```

Result: failed only because the current Codex environment blocks local socket creation for Playwright/live-server tests:

- `tests/test_playwright_collection.py::test_collection_browser_acceptance`
- `tests/test_playwright_crm.py::test_crm_browser_acceptance`
- `tests/test_playwright_launch_acceptance.py::test_launch_browser_acceptance`
- `tests/test_playwright_outreach_inbound.py::test_outreach_inbound_browser_acceptance`

The error is `PermissionError: [Errno 1] Operation not permitted` from `socket.socket()` during `werkzeug.serving.make_server(...)`.

## Known Risks

- Real MiMo validation is not run because no real provider credentials were used.
- SQLite quota accounting is suitable for beta low concurrency but can overrun under simultaneous requests; PostgreSQL row locks should be added when production concurrency grows.
- AI requests are synchronous with provider timeout. This is acceptable for the current low-memory beta but should move to an async job if usage increases.
- Admin AI page is intentionally minimal and may need better operational UX after real provider testing.

## Review Verdict

READY_FOR_MIMOCODE_REVIEW.

Do not deploy until MiMoCode validates:

- Alembic upgrade on staging.
- Admin `/admin/ai` flow.
- Fake provider draft generation in browser.
- OpenAI-compatible/MiMo provider with redacted real credentials.
- Playwright/browser acceptance tests in an environment with socket access.
