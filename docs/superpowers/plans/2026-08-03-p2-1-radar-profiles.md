# P2-1 Competitor Profile Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an authenticated tenant manually request evidence-cited competitor suggestions for one active Acquisition Mission, then approve or dismiss each suggestion into a tenant-owned competitor profile.

**Architecture:** A new explicit `COMPETITOR_RADAR` capability remains disabled by default. Radar owns tenant-scoped suggestions, profiles, policy validation, and UI projections; it reads Mission/ProductSnapshot through Acquisition repositories and appends AuditEvents within the same transaction. A public MiMo adapter produces only a strict cited proposal schema; no page fetch, Browser run, job, Candidate, CRM, notification, or scheduler is added.

**Tech Stack:** Flask, SQLAlchemy 2, Alembic, Pydantic 2, existing MiMo adapter, pytest, Jinja templates.

---

## Fixed decisions

- `COMPETITOR_RADAR` maps to `COMPETITOR_RADAR_ENABLED`, is an explicit opt-in capability, and defaults false in all modes including tests.
- The P2-1 active Mission statuses are `queued`, `running`, and `paused`; draft and terminal Missions cannot receive suggestions or profiles.
- A suggestion must contain an official HTTP(S) URL, a public source URL, a bounded excerpt, at least one reason code, and a canonical public domain. Model confidence is not persisted or used as evidence.
- A dismissed suggestion is reopened in-place only when its SHA-256 source-evidence hash changes; the tenant/mission/domain uniqueness remains intact.
- An approved profile starts `active` with `{"seed_urls":[official_url],"allowed_page_kinds":["home"]}`. P2-1 does not run or fetch the seed.

## File structure

- Create: `app/modules/radar/__init__.py`, `contracts.py`, `models.py`, `repository.py`, `policies.py`, `suggestions.py`, `service.py`, `routes.py`, `views.py`.
- Create: `app/templates/radar/overview.html`, `suggestions.html`, `profile_detail.html`.
- Create: `migrations/versions/0016_radar_profiles.py`.
- Create: `tests/radar/conftest.py`, `test_models.py`, `test_repositories.py`, `test_suggestions.py`, `test_routes.py`.
- Modify: `app/core/capabilities.py`, `app/__init__.py`, `app/extensions.py`, `app/integrations/ai/contracts.py`, `app/integrations/ai/mimo.py`, `tests/test_capabilities.py`, `tests/test_migration_paths.py`.

### Task 1: Disabled capability and immutable Radar persistence

**Files:** capability service, Radar contracts/models, extension imports, migration, model and capability tests.

- [ ] **Step 1: Write failing tests.**

Assert that `resolve_capabilities("internal")[Capability.COMPETITOR_RADAR]` is false with no environment override, that a test app also keeps it false, and that models enforce tenant/domain uniqueness plus the statuses:

```python
assert profile.status == "active"
assert suggestion.status == "proposed"
with pytest.raises(IntegrityError):
    add_same_tenant_mission_domain_twice()
```

- [ ] **Step 2: Run the tests.**

Run: `python -m pytest -q tests/test_capabilities.py tests/radar/test_models.py`

Expected: FAIL because the Capability and Radar models do not exist.

- [ ] **Step 3: Implement capability, contracts, models, and migration.**

Add `Capability.COMPETITOR_RADAR` to both defaults, `COMPETITOR_RADAR_ENABLED` to the environment map, and to `_EXPLICIT_OPT_IN_CAPABILITIES`.

Create `RadarCompetitorSuggestion` with tenant/mission/domain unique constraint, bounded fields, `evidence_hash`, `reason_codes_json`, `evidence_json`, and `proposed|approved|dismissed` constraint. Create `CompetitorProfile` with tenant/mission/domain uniqueness, the Mission ProductSnapshot ID, source suggestion ID, bounded tracking JSON, and `active|paused|archived` constraint. Register Radar models before Alembic metadata is used.

Migration `0016_radar_profiles` revises `0015_browser_foundation`, creates both tables and indexes, and has a complete reverse downgrade.

- [ ] **Step 4: Re-run the focused tests and commit.**

Run: `python -m pytest -q tests/test_capabilities.py tests/radar/test_models.py`

Commit: `feat(radar): add tenant-owned profile domain`.

### Task 2: Tenant repositories and policy validation

**Files:** `repository.py`, `policies.py`, repository tests.

- [ ] **Step 1: Write failing tenant-isolation and policy tests.**

Test that every public get/list/create method requires `tenant_id`; foreign-tenant IDs return no object; a profile cannot be created for a draft, completed, failed, or cancelled Mission; a ProductSnapshot from another tenant or different Mission snapshot is rejected.

- [ ] **Step 2: Run the tests.**

Run: `python -m pytest -q tests/radar/test_repositories.py`

Expected: FAIL because repositories and policies do not exist.

- [ ] **Step 3: Implement repositories and pure policy functions.**

Repositories query each ID with `tenant_id`, order list projections deterministically, and never accept a model instance whose tenant differs from the caller. Policy functions parse only bounded JSON, canonicalize HTTPS/HTTP URLs through `validate_public_url`, derive the canonical domain, and produce a stable evidence hash from canonical JSON. Only `queued|running|paused` Missions pass `require_active_mission`.

- [ ] **Step 4: Re-run and commit.**

Run: `python -m pytest -q tests/radar/test_repositories.py tests/radar/test_models.py`

Commit: `feat(radar): enforce profile tenant policies`.

### Task 3: Cited suggestion generation and idempotent decisions

**Files:** AI contracts/adapter, Radar suggestions/service, suggestion tests.

- [ ] **Step 1: Write failing proposal-validation tests.**

Use a fake provider and public-IP resolver. Assert no suggestion persists when the proposal lacks cited evidence, has an unsafe official/source URL, repeats a profile domain, has more than ten entries, or is for a cross-tenant/non-active Mission. Assert valid input stores stable evidence JSON and a dismiss/re-request with unchanged evidence remains dismissed.

- [ ] **Step 2: Run the tests.**

Run: `python -m pytest -q tests/radar/test_suggestions.py`

Expected: FAIL because Radar suggestion service does not exist.

- [ ] **Step 3: Add a strict public MiMo proposal contract.**

Add Pydantic models with `extra="forbid"`: `CompetitorEvidenceProposal(source_url, excerpt)`, `CompetitorSuggestionProposal(company_name, official_url, reason_codes, evidence)`, and `CompetitorSuggestionResults(suggestions)`. Bounds: 10 suggestions, 200-character name, 10 reason codes of 80 characters, two evidence entries of 1,000-character excerpts.

Add `MiMoProvider.suggest_competitors(product_summary, target_profile)`, backed by a dedicated JSON prompt and web-search enabled request. It returns only schema-valid results; no confidence field is accepted.

- [ ] **Step 4: Implement request and decision services.**

`request_competitor_suggestions(app, tenant_id, actor_id, mission_id)` requires Radar and AI research capabilities, the active tenant-owned Mission, and its matching tenant ProductSnapshot. It validates every proposal before persistence, skips existing profiles, and returns at most ten persisted IDs. It appends only safe audit events.

`decide_competitor_suggestion(..., action)` accepts only `approve` or `dismiss`. Approval is one transaction: re-read tenant-owned suggestion, validate active Mission/snapshot, obtain-or-create exactly one profile, mark suggestion approved, and append audit. Repeated approval returns the same profile; repeated dismissal is idempotent. No decision calls external AI or fetch code.

- [ ] **Step 5: Re-run and commit.**

Run: `python -m pytest -q tests/radar/test_suggestions.py tests/radar/test_repositories.py`

Commit: `feat(radar): add cited competitor suggestions`.

### Task 4: Authenticated manual UI

**Files:** Radar routes/views/templates, route tests, app factory import.

- [ ] **Step 1: Write failing route tests.**

Using a session-authenticated tenant user, assert:
- `GET /radar` shows only that tenant's profiles;
- `GET /radar/missions/<id>/suggestions` returns 404 for another tenant;
- all POST actions require CSRF, capability, and membership;
- repeated approve/dismiss POSTs redirect to the same tenant-owned resource;
- templates display company name, official URL, cited source URL/excerpt, reason codes, and non-color status text.

- [ ] **Step 2: Run the tests.**

Run: `python -m pytest -q tests/radar/test_routes.py`

Expected: FAIL because Radar routes are not registered.

- [ ] **Step 3: Implement the minimal UI.**

Register `register_radar_routes` in the app factory. The overview lists profiles and active Missions. The suggestion page performs an explicit POST to request suggestions; no GET has side effects. Approve/dismiss remain POST-only and use standard CSRF. Views use repositories/services only; templates have no fetch/run/delete controls.

- [ ] **Step 4: Re-run and commit.**

Run: `python -m pytest -q tests/radar/test_routes.py`

Commit: `feat(radar): add manual profile review UI`.

### Task 5: Migration and slice acceptance

**Files:** migration-path tests and P2-1 evidence only.

- [ ] **Step 1: Add a failing `0015 -> 0016 -> 0015 -> 0016` migration-path test.**

- [ ] **Step 2: Implement no production code; update the expected head only.**

- [ ] **Step 3: Run full applicable gates.**

```powershell
python -m alembic heads
python -m pytest -q tests/radar tests/test_capabilities.py tests/test_migration_paths.py
python -m pytest -q -k "not browser"
python -m ruff check app/modules/radar app/integrations/ai tests/radar
python -m ruff format --check app/modules/radar app/integrations/ai tests/radar
git diff --check
```

Expected: one Alembic head `0016_radar_profiles`; no cross-tenant leak; no direct browser/fetch/Candidate/outreach behavior.

- [ ] **Step 4: Record P2-1 evidence, obtain code/security/product review, fix findings, and commit only the named slice files.**

## P2-1 exit criteria

- [ ] Capability is default-off and every Radar route/service enforces it.
- [ ] All persisted Radar objects are tenant-owned and tenant-scoped.
- [ ] Every proposal is schema-valid, URL-policy checked, evidence-cited, and capped at ten.
- [ ] Approval/dismissal are idempotent; profile creation is atomic and human initiated.
- [ ] No crawler, Browser task, Radar run, Candidate/Evidence conversion, CRM action, notification, or schedule exists.
- [ ] Migration roundtrip and full non-browser regression pass.

