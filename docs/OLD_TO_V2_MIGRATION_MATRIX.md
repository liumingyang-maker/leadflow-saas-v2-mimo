# Old Project to V2 Migration Matrix

Source of truth: old repository `C:/Users/97020/Desktop/leads-saas` read from `origin/main` at commit `c7e77f6` plus its P0 test suite and route snapshot. The old repository is read-only for V2 work.

## Product Flow Mapping

| Old capability | Old evidence | V2 target module | V2 milestone | Migration rule |
|---|---|---|---|---|
| Landing, terms, privacy | `/`, `/terms`, `/privacy` | `app.modules.core` + templates | V2-01/V2-06 | Rebuild as simple server-rendered pages; do not copy old page structure wholesale. |
| Registration, login, logout, verification, password reset | `/register`, `/login`, `/logout`, `/verify-email/<token>`, `/forgot-password`, `/reset-password/<token>` | `app.modules.auth` | V2-02 | Preserve flows and P0 security behavior; implement with Application Factory, CSRF, service/repository split. |
| Tenant onboarding and product profile | `/onboarding/<step>`, `/product-profile/generate` | `app.modules.tenants` | V2-02/V2-03 | Keep product profile and target-market setup, but reduce to V2 core profile contract. |
| Workbench/dashboard | `/workbench`, `/dashboard` | `app.modules.dashboard` | V2-06 | Preserve "today's action" information architecture using Signal Workspace UI. |
| Lead review and detail | `/leads`, `/lead/<lead_id>` and lead mutation routes | `app.modules.leads` | V2-03 | Keep review queue, accept/ignore/research/update actions, and tenant-scoped lead ownership. |
| CRM | `/crm`, stage/follow-up/deal/tags/note routes | `app.modules.crm` | V2-03 | Preserve stages: new, to_contact, contacted, replied, opportunity, won, closed. |
| Import | `/import`, `/import/upload`, `/import/confirm` | `app.modules.collection` + import adapter | V2-03/V2-04 | Support CSV/XLSX import through adapters and review queue. |
| Collection | `/collect`, `/run/<step>`, `/task/<task_id>` | `app.modules.collection`, `app.modules.jobs` | V2-04 | Web enqueues persistent tenant-owned jobs; worker executes service layer. |
| Outreach | email template, send email, tracking, unsubscribe, deliverability | `app.modules.outreach` | V2-05 | Keep single-send and logged follow-up; freeze large-scale cold automation. |
| Inbound widget API | `/inbound`, `/api/inbound/<token>` | `app.modules.inbound` | V2-05 | Preserve hardened token, rate-limit, idempotency, allowlist, honeypot contracts. |
| Billing and plans | `/upgrade`, `/pay/*` | `app.modules.billing` | V2-06 | Keep provider abstraction and idempotent callbacks; use mocks locally without real payment credentials. |
| Admin | `/admin/*` | `app.modules.admin` | V2-06 | Preserve no-default-admin rule, first password change, tenant status controls, and audit boundary. |
| Competitor radar | `/radar*` | frozen or `app.modules.radar` later | Frozen through V2-06 unless needed for launch acceptance | Keep data model awareness; do not prioritize in core V2 loop. |

## Data Contract Seeds

| Domain | Old fields observed | V2 contract |
|---|---|---|
| Tenant | `id`, `email`, `password_hash`, `company_name`, `status`, `plan`, `trial_ends`, `plan_expires_at`, `email_verified`, `onboarding_done`, timestamps | SQLAlchemy `Tenant`, `User`, and `TenantMembership`; status and plan guarded on every protected request. |
| Admin user | `id`, `email`, `password_hash`, `must_change_password`, timestamps | Separate admin model/session boundary; no default password, CLI-created admin only. |
| Email token | `token`, `tenant_id`, `email`, `type`, `used`, `expires_at` | Token model with atomic consume for verification and reset. |
| Lead | company, country, website, email, phone, source, status, stage, grade/score, tags, notes, deal fields, timestamps | Tenant-scoped `Lead` with review status, CRM stage, quality dimensions, contact fields, and timeline events. |
| Lead activity | `id`, `lead_id`, `type`, `content`, `created_at` | Tenant-scoped activity/timeline table; no template-direct DB access. |
| Job/task | `id`, `tenant_id`, `task_type`, `status`, `progress`, `result_json`, `error_message`, timestamps | Persistent `Job` with tenant ownership, idempotency key, progress events, and sanitized errors. |
| Inbound token | token digest/ciphertext, `tenant_id`, timestamps | Encrypted token storage, digest lookup, rotation, no plaintext display. |
| Inbound protection | rate limits and idempotency tables | Persistent limits by token/IP and tenant plus idempotency by tenant/token/key/payload. |
| Outreach tracking | `tracking_id`, `tenant_id`, `lead_id`, subject, open/click counts | Signed click targets, safe redirect validation, tenant-scoped tracking stats. |
| Suppression/send counter | `tenant_id`, email/day counts | Tenant-scoped suppression and quota tables. |
| Orders/coupons | order, provider, status, amount, coupon fields | Idempotent billing model; real providers disabled in local mocks. |

## P0 Security Contracts to Carry Forward

| Old P0 task | Required V2 behavior | Old test reference |
|---|---|---|
| P0-000 baseline | Route snapshots and smoke tests must pin behavior before refactors. | `tests/test_url_map.py`, `tests/test_smoke.py` |
| P0-001 no default admin | Empty DB creates no weak admin; CLI creation requires strong password and first change. | `tests/test_admin_security.py` |
| P0-002 global CSRF | All browser writes require CSRF, narrow documented exemptions only. | `tests/test_csrf.py` |
| P0-003 tenant-owned tasks | Jobs are UUIDs, persistent, tenant-scoped on reads and updates, and sanitize errors. | `tests/test_task_isolation.py` |
| P0-004 signed click redirects | Unsigned/tampered/private-network redirect targets fail and do not count clicks. | `tests/test_click_tracking_security.py` |
| P0-005 cookie/proxy/account guard | Secure production cookies, opt-in proxy headers, session rotation, suspended/expired guards. | `tests/test_cookie_proxy_guard.py` |
| P0-006 encrypted tenant secrets | Secrets encrypt at rest, mask in UI, preserve on empty submit, support rotation. | `tests/test_tenant_secret_store.py` |
| P0-007 hardened inbound API | Strong tokens, origin allowlist, size/type validation, field whitelist, honeypot, persistent rate limits, idempotency. | `tests/test_inbound_security.py` |

## Frozen or Deferred Features

Frozen for V2 launch unless a later task explicitly reopens them: Facebook/TikTok scraping, Zauba, Alibaba RFQ, unstable site crawlers, large-scale cold email automation, complex marketing automation, full competitor radar expansion, and broad BYOK marketplace connectors.

## Implementation Guardrails

- Do not copy old `web/app.py` or continue its monolithic structure.
- Preserve effective product behavior, security boundaries, data fields, tests, and UI information architecture.
- New code goes only into the V2 repository.
- Old repository access remains read-only and evidence-based.
- External integrations must be adapters with safe fake/mock implementations for local tests when real credentials are unavailable.
