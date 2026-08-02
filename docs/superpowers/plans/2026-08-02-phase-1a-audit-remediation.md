# Phase 1A Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the confirmed Phase 1A audit gaps without changing the existing Mission, Candidate, Evidence, Assessment, Lead, tenant-isolation, or future SaaS architecture.

**Architecture:** Keep one evidence pipeline. MiMo URL extraction and deterministic manual facts both produce `ExtractedCompanyFacts`, then reuse the existing Candidate/Evidence/Assessment/CRM flow. Human decision states are immutable to background retries. Scoring advances by creating `priority-v2` assessments rather than rewriting `priority-v1`. Local file SQLite receives bounded connection hardening; PostgreSQL and in-memory SQLite remain unchanged.

**Tech Stack:** Python 3.12, Flask, Jinja/HTMX, Pydantic 2, SQLAlchemy 2, SQLite, RQ/Redis, httpx, pytest, Ruff, Alembic.

---

## Fixed scope and execution rules

- Design authority: `docs/superpowers/specs/2026-08-02-phase-1a-audit-remediation-design.md`.
- Baseline branch: `design/solo-ai-acquisition-system`.
- Baseline design commit: `c3293cc`.
- Do not modify or stage `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png`; it is user-owned evidence.
- Do not launch Playwright or issue bursts of browser commands. The operator reported application crashes from that pattern.
- Do not add migrations: every change in this plan uses existing columns and tables.
- Do not add outreach sending, browser automation, LinkedIn automation, public signup, or automatic policy updates.
- Every repository/service lookup remains tenant-scoped. Cross-tenant resources return 404 at the route boundary.
- Every route uses the existing Flask-WTF CSRF protection and session identity; never accept `tenant_id` or `actor_id` from form fields.
- Run each task's focused tests before its commit. Keep commits small and use the exact commit subjects listed below.

## Task 1: Make human decisions immutable to assessment retries

**Files:**

- Create: `app/modules/acquisition/states.py`
- Modify: `app/modules/acquisition/jobs.py:451-569`
- Modify: `app/modules/acquisition/service.py:451-511,851-962`
- Modify: `tests/acquisition/test_jobs.py:202-332`
- Modify: `tests/acquisition/test_service.py:305-335`

- [ ] **Step 1: Add failing regression coverage for all human terminal states**

Extend `test_discovery_verify_and_assess_handlers_preserve_evidence_boundary` after the first successful assessment. For each status, persist distinct human fields, rerun the same assessment handler, then compare the stored tuple exactly:

```python
human_cases = (
    ("accepted", "", "reviewer-accepted"),
    ("promoted", "", "reviewer-promoted"),
    ("rejected", "wrong_buyer_type", "reviewer-rejected"),
)
for status, reason, actor in human_cases:
    decided_at = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        candidate.status = status
        candidate.eligibility_code = "human-terminal"
        candidate.decision_reason_code = reason
        candidate.decided_by = actor
        candidate.decided_at = decided_at
        session.commit()

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        expected_human_fields = (
            candidate.status,
            candidate.eligibility_code,
            candidate.decision_reason_code,
            candidate.decided_by,
            candidate.decided_at,
        )

    handle_candidate_assess(acquisition_app, assess_job, {"candidate_id": candidate_id})

    with Session(get_engine(acquisition_app)) as session:
        candidate = session.get(AcquisitionCandidate, candidate_id)
        assert candidate is not None
        assert (
            candidate.status,
            candidate.eligibility_code,
            candidate.decision_reason_code,
            candidate.decided_by,
            candidate.decided_at,
        ) == expected_human_fields
        assert session.scalar(select(func.count()).select_from(CandidateAssessment)) == 1
```

Run:

```powershell
python -m pytest tests/acquisition/test_jobs.py::test_discovery_verify_and_assess_handlers_preserve_evidence_boundary -q
```

Expected before implementation: failure because `handle_candidate_assess` replaces the human status and eligibility code.

- [ ] **Step 2: Define one shared terminal-state constant**

Create `app/modules/acquisition/states.py`:

```python
"""State invariants shared by acquisition services and workers."""

from __future__ import annotations

HUMAN_TERMINAL_STATUSES = frozenset({"accepted", "promoted", "rejected"})
```

Import this constant in `jobs.py` and `service.py`. Replace both inline terminal-state sets with the shared constant. In `handle_candidate_assess`, guard both state fields, while still updating current score fields:

```python
if candidate.status not in HUMAN_TERMINAL_STATUSES:
    candidate.status = gate.disposition
    candidate.eligibility_code = gate.reason_codes[0] if gate.reason_codes else "eligible"
candidate.priority_score = score.priority_score
candidate.priority_band = score.priority_band
candidate.signal_coverage = score.signal_coverage
```

Do not clear or rewrite `decision_reason_code`, `decided_by`, or `decided_at` anywhere in an assessment handler.

- [ ] **Step 3: Make country override legal only from `needs_evidence`**

Add a parameterized service test using `_seed_mission_and_candidate`:

```python
@pytest.mark.parametrize("status", ["eligible", "accepted", "promoted", "rejected"])
def test_country_override_rejects_non_evidence_states(acquisition_app, status):
    from app.modules.acquisition.service import AcquisitionError, override_candidate_country

    candidate_id = _seed_mission_and_candidate(
        acquisition_app,
        status=status,
        eligibility_code="country_unknown",
        suffix=f"country-{status}",
    )
    with pytest.raises(AcquisitionError, match="needs evidence"):
        override_candidate_country(
            acquisition_app,
            tenant_id="t1",
            actor_id="u1",
            candidate_id=candidate_id,
            country_code="MX",
            source_url="https://moto.example/contact",
            reason_code="official_contact_page",
        )
```

Immediately after loading the candidate in `override_candidate_country`, add:

```python
if candidate.status != "needs_evidence":
    raise AcquisitionError("only candidates that need evidence can override country")
```

Keep the current queue behavior in this task so the commit is isolated; Task 6 replaces it with synchronous evidence-backed reassessment.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_jobs.py tests/acquisition/test_service.py -q
python -m ruff check app/modules/acquisition/states.py app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
git diff --check
```

Expected: both test files pass; Ruff reports `All checks passed!`; `git diff --check` prints nothing.

Commit:

```powershell
git add app/modules/acquisition/states.py app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
git commit -m "fix(acquisition): preserve human candidate decisions"
```

## Task 2: Introduce immutable `priority-v2` scoring

**Files:**

- Create: `app/modules/acquisition/versions.py`
- Modify: `app/modules/acquisition/scoring.py:107-159`
- Modify: `app/modules/acquisition/jobs.py:536-560`
- Modify: `app/modules/acquisition/service.py:578,769,924-952`
- Modify: `tests/acquisition/test_scoring.py`
- Modify: `tests/acquisition/test_jobs.py`
- Modify: `tests/acquisition/test_service.py`

- [ ] **Step 1: Write failing score-band tests**

Add a helper that supplies all Fit and Data Quality values at 100 with every Intent value `None`. Assert that the result is provisional and capped at A. Add a second input with at least one known Intent value and assert S is possible:

```python
def test_provisional_priority_is_capped_at_a_even_with_high_known_signals():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    result = score_candidate(
        ScoreInput(
            product_relevance=100,
            buyer_role=100,
            country_match=100,
            company_size=100,
            industry_match=100,
            direct_purchase=None,
            recent_activity=None,
            competitor_signal=None,
            signal_recency=None,
            identity_quality=100,
            source_trust=100,
            contactability=100,
            independent_evidence=100,
            data_recency=100,
        )
    )
    assert result.priority_mode == "fit_quality_provisional_v1"
    assert result.priority_band == "A"


def test_full_priority_can_receive_s_when_intent_is_known():
    from app.modules.acquisition.scoring import ScoreInput, score_candidate

    values = {field: 100 for field in ScoreInput.__dataclass_fields__}
    result = score_candidate(ScoreInput(**values))
    assert result.priority_mode == "full_v1"
    assert result.priority_band == "S"
```

Run:

```powershell
python -m pytest tests/acquisition/test_scoring.py -q
```

Expected before implementation: the provisional test receives S and fails.

- [ ] **Step 2: Cap S by score mode, not by changing weights**

Change `_band` and its caller only:

```python
def _band(score: int | None, coverage: int, mode: str) -> str:
    if score is None:
        return "unknown"
    if score >= 85 and coverage >= 60 and mode == "full_v1":
        return "S"
    if score >= 70:
        return "A"
    if score >= 55:
        return "B"
    return "C"
```

In `score_candidate`, compute `mode` before the return and call `_band(priority, total_coverage, mode)`. Do not change weights or coverage calculations.

- [ ] **Step 3: Centralize versions and write only `priority-v2` going forward**

Create `app/modules/acquisition/versions.py`:

```python
"""Version identifiers for immutable acquisition assessments."""

ELIGIBILITY_POLICY_VERSION = "eligibility-v1"
PRIORITY_SCORE_VERSION = "priority-v2"
MIMO_EXTRACT_PROMPT_VERSION = "company-extract-v1"
MANUAL_FACTS_PROMPT_VERSION = "manual-facts-v1"
COUNTRY_EVIDENCE_PROMPT_VERSION = "country-evidence-v1"
```

Replace write-path literals in `jobs.py` and `_assess_candidate_in_session` with these constants. Do not update stored rows. Update fallback display literals in `service.py` only when they describe the current scoring implementation.

Extend the existing job/service tests with:

```python
assert assessment.score_version == "priority-v2"
```

Add a preservation test that inserts a `CandidateAssessment` with `score_version="priority-v1"`, runs the current assessment, and asserts one v1 row plus one v2 row remain. The v1 row's JSON and timestamps must be unchanged.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_scoring.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py -q
python -m ruff check app/modules/acquisition tests/acquisition
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/versions.py app/modules/acquisition/scoring.py app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_scoring.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
git commit -m "feat(acquisition): version provisional priority scoring"
```

## Task 3: Build deterministic manual-evidence validation

**Files:**

- Modify: `app/modules/acquisition/contracts.py`
- Create: `app/modules/acquisition/manual_evidence.py`
- Create: `tests/acquisition/test_manual_evidence.py`

- [ ] **Step 1: Define strict form contracts**

Add these Pydantic models to `contracts.py`, reusing `_is_country_code` and `ALLOWED_BUYER_TYPES`:

```python
class ManualCompanyFactsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=1000)
    company_name: str = Field(min_length=1, max_length=300)
    opportunity_country_code: str = Field(pattern=r"^[A-Z]{2}$")
    buyer_type: str = Field(min_length=1, max_length=120)
    evidence_text: str = Field(min_length=3, max_length=1000)
    contact_path: str = Field(min_length=3, max_length=1000)

    @field_validator("opportunity_country_code")
    @classmethod
    def validate_country(cls, value: str) -> str:
        clean = value.strip().upper()
        if not _is_country_code(clean):
            raise ValueError("invalid ISO alpha-2 country code")
        return clean

    @field_validator("buyer_type")
    @classmethod
    def validate_buyer_type(cls, value: str) -> str:
        clean = value.strip().lower()
        if clean not in ALLOWED_BUYER_TYPES:
            raise ValueError("unsupported buyer type")
        return clean


class CountryEvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    source_url: str = Field(min_length=8, max_length=1000)
    evidence_text: str = Field(min_length=3, max_length=1000)
    reason_code: Literal[
        "official_contact_page", "registry_record", "manual_verification", "other"
    ]
```

Give `CountryEvidenceInput.country_code` the same country validator. URL network safety remains `StaticFetcher`'s responsibility; Pydantic only bounds shape and size.

- [ ] **Step 2: Write failing pure-unit tests for normalized support and contact rules**

Create tests that cover:

- Unicode NFKC, case folding, and whitespace collapse allow a real sentence match.
- A sentence absent from sanitized page text raises `ManualEvidenceError`.
- Email, `mailto:`, and a 7-25 character phone present in page text are accepted.
- An absent email/phone is rejected.
- A contact URL is accepted only when `normalise_domain` of its hostname equals the fetched final URL domain.
- A contact URL on a different domain is rejected before any second fetch.
- Generated claims always cite `snapshot.final_url`; a submitted domain is never accepted.

Run:

```powershell
python -m pytest tests/acquisition/test_manual_evidence.py -q
```

Expected before implementation: import failure for the new module.

- [ ] **Step 3: Implement deterministic normalization and fact construction**

Create `manual_evidence.py` with these public entry points:

```python
class ManualEvidenceError(ValueError):
    pass


def normalize_evidence_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def require_supported_text(*, claim: str, page_text: str) -> str:
    clean_claim = " ".join(claim.split())
    if normalize_evidence_text(clean_claim) not in normalize_evidence_text(page_text):
        raise ManualEvidenceError("submitted evidence is not present in the fetched page")
    return clean_claim


def contact_url(value: str) -> str | None:
    parsed = urlsplit(value.strip())
    return value.strip() if parsed.scheme.lower() in {"http", "https"} else None


def normalise_domain(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").rstrip(".").lower()
    return host.removeprefix("www.")


def build_manual_company_facts(
    value: ManualCompanyFactsInput,
    *,
    primary: FetchResult,
    contact_snapshot: FetchResult | None,
) -> ExtractedCompanyFacts:
```

The implementation must:

1. match `evidence_text` against `primary.text`;
2. derive `canonical_domain` from `primary.final_url` after stripping only a leading `www.`;
3. accept a URL contact only when its normalized domain equals the primary domain and `contact_snapshot.final_url` remains on that domain;
4. accept non-URL contact paths only when a bounded email, `mailto:`, or phone appears in the primary or contact page text;
5. emit `EvidenceClaim(claim_id="manual-product-evidence", ...)` for the evidence sentence;
6. emit no AI inferences; store explicit unknowns only when a field is genuinely absent.

Do not resolve DNS or fetch inside this pure module. The service does both through `StaticFetcher` in Task 4.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_manual_evidence.py -q
python -m ruff check app/modules/acquisition/contracts.py app/modules/acquisition/manual_evidence.py tests/acquisition/test_manual_evidence.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/contracts.py app/modules/acquisition/manual_evidence.py tests/acquisition/test_manual_evidence.py
git commit -m "feat(acquisition): validate deterministic manual evidence"
```

## Task 4: Persist manual and MiMo URL modes through one evidence pipeline

**Files:**

- Modify: `app/modules/acquisition/service.py:185-270,851-962`
- Modify: `tests/acquisition/test_service.py:208-255`
- Modify: `tests/acquisition/test_phase_1a_acceptance.py:116-160`

- [ ] **Step 1: Add failing service tests for complete MiMo outage**

Add `test_manual_facts_need_no_mimo_and_are_idempotent`. Use a fake `StaticFetcher` returning a real `FetchResult`, call the new service twice with identical `ManualCompanyFactsInput`, and assert:

```python
assert first.id == second.id
assert first.status == "eligible"
assert first.source_channel == "manual_url"
assert candidate_count == 1
assert evidence_count == 1
assert assessment_count == 1
assert assessment.model_provider == "manual"
assert assessment.model_id == "human-confirmed-v1"
assert assessment.prompt_version == "manual-facts-v1"
assert assessment.score_version == "priority-v2"
```

Add a second test where a same-domain contact URL is supplied. The fake fetcher must record two calls and return primary/contact `FetchResult` objects; assert both Evidence rows are saved once. Add failure tests for absent evidence text and cross-domain contact; assert zero Candidate and zero Evidence rows.

Run:

```powershell
python -m pytest tests/acquisition/test_service.py -k "manual" -q
```

Expected before implementation: `process_manual_facts` cannot be imported.

- [ ] **Step 2: Extract one persistence helper from `process_manual_url`**

Create a private helper with an explicit assessment provenance:

```python
@dataclass(frozen=True)
class AssessmentProvenance:
    provider: str
    model_id: str
    prompt_version: str


def _persist_url_candidate(
    session: Session,
    *,
    app,
    tenant_id: str,
    mission: AcquisitionMission,
    facts: ExtractedCompanyFacts,
    snapshots: tuple[FetchResult, ...],
    provenance: AssessmentProvenance,
) -> AcquisitionCandidate:
```

Move the existing Candidate dedupe, `_apply_extracted_facts`, Evidence dedupe, and assessment call into this helper. For each snapshot, compute `supports_json` from only claims whose `source_url` equals that snapshot's `final_url`. Accept observed claims only when every source URL belongs to `snapshots`; otherwise raise before database writes.

Change `_assess_candidate_in_session` to accept `provenance` and use it in `find_input_version` and `CandidateAssessment`. Its defaults must preserve existing MiMo calls:

```python
MIMO_PROVENANCE = AssessmentProvenance(
    provider="mimo",
    model_id="",
    prompt_version=MIMO_EXTRACT_PROMPT_VERSION,
)
```

When `model_id` is empty, resolve it from `app.config["MIMO_MODEL"]`. Manual calls pass all three values explicitly.

- [ ] **Step 3: Implement the no-MiMo service path**

Add:

```python
def process_manual_facts(
    app,
    *,
    tenant_id: str,
    mission_id: str,
    value: ManualCompanyFactsInput,
    fetcher: StaticFetcher,
) -> AcquisitionCandidate:
```

Sequence:

1. Verify the tenant-scoped Mission exists and `manual_url` is allowed by `channel_policy_json`.
2. Fetch `value.url` with `StaticFetcher` and reject prompt injection.
3. If `contact_url(value.contact_path)` returns a URL, compare its normalized domain with the primary final URL before fetching it, then fetch and recheck its final domain after redirects.
4. Build facts with `build_manual_company_facts`.
5. Open a new transaction and re-read the Mission tenant-scoped.
6. Call `_persist_url_candidate` with `AssessmentProvenance("manual", "human-confirmed-v1", MANUAL_FACTS_PROMPT_VERSION)`.
7. Commit once after Candidate, all Evidence, and Assessment are valid.

Keep `process_manual_url` as the MiMo/generic extractor entry point. It performs the same tenant-scoped channel check, fetches once, calls the extractor, and delegates to the same persistence helper with MiMo provenance. It must remain backward compatible with existing service and acceptance tests. In both modes, `_persist_url_candidate` derives the Candidate domain from the safe primary `final_url`; it does not trust `facts.canonical_domain` from either the form or the model.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_service.py tests/acquisition/test_phase_1a_acceptance.py -q
python -m ruff check app/modules/acquisition/service.py tests/acquisition/test_service.py tests/acquisition/test_phase_1a_acceptance.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/service.py tests/acquisition/test_service.py tests/acquisition/test_phase_1a_acceptance.py
git commit -m "feat(acquisition): persist manual fallback facts"
```

## Task 5: Expose the two-level manual URL flow in the Mission UI

**Files:**

- Modify: `app/modules/acquisition/routes.py:1-36,161-214,394-434`
- Modify: `app/templates/acquisition/mission_detail.html:38-67`
- Modify: `tests/acquisition/test_routes.py`
- Modify: `app/static/css/components.css` only if existing form primitives cannot provide the layout

- [ ] **Step 1: Write route security and behavior tests first**

Add focused tests for:

- GET Mission detail shows “补充企业网址” only when `manual_url` is allowed and Mission is not cancelled.
- POST without CSRF under `csrf_client` returns 400.
- another tenant's Mission returns 404 and calls neither fetcher nor MiMo.
- `mode=ai_extract` calls `StaticFetcher.from_app`, `build_mimo_provider`, and `process_manual_url`, then redirects to the Candidate.
- a `ProviderError` preserves the submitted URL and renders the manual fields with a safe message; raw provider text and API configuration are absent.
- `mode=manual_facts` calls `process_manual_facts` and never calls `build_mimo_provider`.
- `FetchError` renders `safe_summary`, creates no Candidate, and never echoes page text.
- cancelled Mission and Mission without `manual_url` return 409 without fetching.

Patch `app.modules.acquisition.routes.StaticFetcher`, `build_mimo_provider`, and the two service functions; no test may perform real network calls.

Run:

```powershell
python -m pytest tests/acquisition/test_routes.py -k "manual_url" -q
```

Expected before implementation: POST route returns 404 or 405 and form text is absent.

- [ ] **Step 2: Add the production route with explicit modes**

Register exactly:

```python
@app.post("/acquisition/missions/<mission_id>/manual-url")
@tenant_required(app)
def acquisition_mission_manual_url(mission_id: str):
```

Load the Mission tenant-scoped before any fetch. Parse `mode` as either `ai_extract` or `manual_facts`; reject every other value. Build the fetcher only with `StaticFetcher.from_app(app)`.

For `ai_extract`, build `build_mimo_provider(app, tenant_id=tenant_id)` and call `process_manual_url`. For `manual_facts`, construct `ManualCompanyFactsInput` from bounded form fields and call `process_manual_facts`. On success, redirect to `acquisition_candidate_detail`.

Map errors as follows:

- Pydantic/Acquisition/ManualEvidence error: 400;
- unsafe/unreachable fetch: 400 for invalid input, 503 for timeout/unreachable;
- MiMo provider error: 503 and `manual_mode_open=True`;
- missing/cross-tenant Mission: 404;
- cancelled/disallowed channel: 409.

Extend `_render_mission` with `manual_url_form: dict[str, str] | None` and `manual_mode_open: bool`. Pass normalized, bounded form values; never pass exception objects.

- [ ] **Step 3: Add one progressively disclosed form**

In `mission_detail.html`, add a panel before the candidate list:

- URL field and primary button “用 MiMo 提取这个网址”.
- A `<details>` section labeled “MiMo 不可用？手工填写证据”.
- Manual fields: company name, ISO country, buyer type, evidence sentence, contact path.
- Both forms include `csrf_input()` and a fixed hidden `mode`.
- Explain that all URLs are fetched through the public-page safety gate and no message is sent.
- Preserve submitted values after errors.
- Do not show internal names such as `ExtractedCompanyFacts`, `StaticFetcher`, or Assessment to the operator.

Use existing `.lf-panel`, `.lf-form-stack`, `.lf-field`, `.lf-button`, and `.lf-muted` classes. Add CSS only when a mobile-width test proves a missing primitive.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_routes.py -q
python -m ruff check app/modules/acquisition/routes.py tests/acquisition/test_routes.py
python -m ruff format --check app/modules/acquisition/routes.py tests/acquisition/test_routes.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/routes.py app/templates/acquisition/mission_detail.html tests/acquisition/test_routes.py app/static/css/components.css
git commit -m "feat(acquisition): expose manual URL fallback"
```

## Task 6: Make country evidence real, synchronous, and Redis-independent

**Files:**

- Modify: `app/modules/acquisition/service.py:451-511`
- Modify: `app/modules/acquisition/routes.py:247-275,437-508`
- Modify: `app/templates/acquisition/_candidate_card.html:16-46`
- Modify: `tests/acquisition/test_service.py:305-335`
- Modify: `tests/acquisition/test_routes.py`

- [ ] **Step 1: Replace the old queue test with evidence-backed expectations**

Change the service test so a fake fetcher returns a `FetchResult` containing the submitted country evidence sentence. Assert:

```python
assert candidate.country_resolution_status == "confirmed"
assert candidate.status == "eligible"
assert candidate.opportunity_country_code == "MX"
assert evidence_count == 1
assert assessment.score_version == "priority-v2"
assert audit_event.action == "candidate.country_overridden"
```

Patch `create_and_enqueue` to raise if called. Add failure cases for absent evidence text, wrong starting status, and prompt injection; each must leave Candidate fields, Evidence count, Assessment count, and AuditEvent count unchanged.

- [ ] **Step 2: Refactor `override_candidate_country` into one transaction**

Change its signature to accept `CountryEvidenceInput` and a `StaticFetcher`. Fetch the source before opening the write transaction. Match `value.evidence_text` with `require_supported_text`. Reject prompt injection.

Inside one transaction:

1. tenant-scoped load Candidate and Mission;
2. require `candidate.status == "needs_evidence"` and eligibility code `country_unknown` or `country_conflicting`;
3. update country fields and set `status="verifying"`;
4. add a deduplicated `CandidateEvidence` using fetched final URL/content hash and `supports_json='["country-evidence"]'`;
5. write `candidate.country_overridden` with a safe summary containing country and reason only, never URL query or evidence text;
6. call `_assess_candidate_in_session` synchronously with `AssessmentProvenance("manual", "human-confirmed-v1", COUNTRY_EVIDENCE_PROMPT_VERSION)`;
7. commit once and return the refreshed Candidate.

Delete the `create_and_enqueue` call from this service. Country scoring is deterministic and fast, so the local manual path must work when Redis is unavailable.

- [ ] **Step 3: Add the exact route and conditional card form**

Register:

```python
@app.post("/acquisition/candidates/<candidate_id>/country-evidence")
@tenant_required(app)
def acquisition_candidate_country_evidence(candidate_id: str):
```

Construct `CountryEvidenceInput` from the form and call `override_candidate_country` with `StaticFetcher.from_app(app)`. For HTMX success, return `_render_candidate_card`; otherwise redirect to Candidate detail. Render safe 400/409 errors through `_render_candidate`.

In `_candidate_card.html`, show the country evidence form only when:

```jinja2
{% if candidate.status == 'needs_evidence'
      and candidate.eligibility_code in ['country_unknown', 'country_conflicting'] %}
```

Fields: ISO country, source URL, exact evidence sentence, structured reason. Include CSRF and use the existing HTMX outerHTML target.

Add route tests for CSRF, cross-tenant 404, conditional visibility, successful HTMX replacement, and illegal-state no-write behavior.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_service.py tests/acquisition/test_routes.py -q
python -m ruff check app/modules/acquisition/service.py app/modules/acquisition/routes.py tests/acquisition/test_service.py tests/acquisition/test_routes.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/service.py app/modules/acquisition/routes.py app/templates/acquisition/_candidate_card.html tests/acquisition/test_service.py tests/acquisition/test_routes.py
git commit -m "feat(acquisition): close country evidence loop"
```

## Task 7: Clarify provisional scores and correct the workbench prerequisite

**Files:**

- Modify: `app/modules/acquisition/routes.py:477-508`
- Modify: `app/templates/acquisition/_candidate_card.html:7-11,61-101`
- Modify: `app/modules/acquisition/workbench.py:85-215`
- Modify: `app/templates/app/workbench.html:40-47`
- Modify: `tests/acquisition/test_routes.py`
- Modify: `tests/acquisition/test_workbench.py:126-135,247-273`

- [ ] **Step 1: Write failing UI and workbench tests**

Seed a provisional assessment and assert Candidate HTML contains both “暂定 A” and “暂无意向信号”, while technical details contain `priority-v2` and `fit_quality_provisional_v1`. Seed a full assessment and assert it does not show “暂无意向信号”.

Replace `test_empty_workbench_points_to_new_mission` with two tests:

```python
def test_empty_workbench_without_product_points_to_product_knowledge(acquisition_app):
    view = load_workbench(acquisition_app, tenant_id="new-tenant")
    assert view.next_action_url == "/acquisition/products"
    assert view.review_url == "/acquisition/products"


def test_empty_workbench_with_product_points_to_new_mission(acquisition_app):
    create_product_snapshot(
        acquisition_app,
        tenant_id="t1",
        actor_id="u1",
        product_name="Engine",
        summary="Motorcycle engine",
        facts=[{"name": "product", "value": "engine"}],
        prohibited_claims=[],
    )
    view = load_workbench(acquisition_app, tenant_id="t1")
    assert view.next_action_url == "/acquisition/missions/new"
    assert view.review_url == "/acquisition/missions/new"
```

- [ ] **Step 2: Compute presentation flags once in the view model**

Extend `_candidate_view`:

```python
priority_mode = assessment.priority_mode if assessment else ""
is_provisional = priority_mode == "fit_quality_provisional_v1"
```

Return `priority_mode` and `is_provisional`. In the card:

- provisional top badge renders `暂定 {{ candidate.priority_band }}`;
- full mode renders `{{ candidate.priority_band }} 优先级`;
- provisional mode includes the sentence “暂无意向信号，当前排序只依据匹配度和数据质量。”;
- technical details show both score version and priority mode.

Do not call missing Intent “low intent”.

- [ ] **Step 3: Gate workbench creation by product knowledge**

Inside the existing tenant-scoped workbench session, query whether one `ProductKnowledgeSnapshot` exists for the tenant. When no review/failure/reply action takes precedence, use `/acquisition/products` if absent and `/acquisition/missions/new` if present. Apply the same fallback to `review_url`.

Pass a boolean such as `has_product_knowledge` to the workbench template or derive button text from the URL. The empty button must say “先添加产品知识” when its URL is `/acquisition/products`.

- [ ] **Step 4: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_routes.py tests/acquisition/test_workbench.py -q
python -m ruff check app/modules/acquisition/routes.py app/modules/acquisition/workbench.py tests/acquisition/test_routes.py tests/acquisition/test_workbench.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/routes.py app/templates/acquisition/_candidate_card.html app/modules/acquisition/workbench.py app/templates/app/workbench.html tests/acquisition/test_routes.py tests/acquisition/test_workbench.py
git commit -m "fix(acquisition): clarify next action and provisional score"
```

## Task 8: Harden file SQLite for one-operator concurrent writers

**Files:**

- Modify: `app/extensions.py:1-43`
- Modify: `app/config.py`
- Create: `tests/acquisition/test_sqlite_runtime.py`
- Modify: `docs/RUNBOOK_BACKUP_RESTORE.md`

- [ ] **Step 1: Write engine-configuration tests first**

Create tests using temporary database paths and `reset_engine_for_tests`:

```python
def test_file_sqlite_enables_wal_and_busy_timeout(tmp_path):
    engine = get_engine(database_uri=f"sqlite:///{tmp_path / 'runtime.db'}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000


def test_memory_sqlite_does_not_enable_wal():
    engine = get_engine(database_uri="sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() != "wal"
```

Add a test with a PostgreSQL-shaped URL only around the pure predicate that decides whether SQLite PRAGMA applies; do not require a live PostgreSQL server.

- [ ] **Step 2: Configure only file-backed SQLite before first connection**

Add a pure predicate and event hook in `extensions.py`:

```python
def _is_file_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite" and engine.url.database not in {None, "", ":memory:"}


def _configure_file_sqlite(engine: Engine, *, busy_timeout_ms: int) -> None:
    if not _is_file_sqlite(engine):
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()
```

Call `_configure_file_sqlite` immediately after `create_engine` and before returning or connecting. Read `SQLITE_BUSY_TIMEOUT_MS` from config with default 5000 and validate it as an integer between 1000 and 30000. The PRAGMA statement uses only this validated integer.

- [ ] **Step 3: Add a bounded concurrency smoke**

Seed a file database through the real app, including one running Mission with terminal child jobs so reconciliation has a real write to perform. Use `ThreadPoolExecutor(max_workers=2)` and a `threading.Barrier(2)` to start:

- one application service write with `create_product_snapshot`;
- one acquisition write with `reconcile_missions` or `_assess_candidate_in_session` through a public service/handler.

Wait at most 10 seconds for both futures. Assert neither raises `OperationalError`, both transactions are visible, and logs/errors do not contain `database is locked`. Keep the one-worker architectural rule; this test covers Web plus reconciler/assessment writers, not two RQ Workers.

- [ ] **Step 4: Clarify WAL-safe backup procedure**

Update `docs/RUNBOOK_BACKUP_RESTORE.md` to state:

- file SQLite runs in WAL mode for Solo local use;
- `.db`, `-wal`, and `-shm` are one live dataset;
- do not copy only `.db` while the application is running;
- use `sqlite3 source.db ".backup 'destination.db'"` or stop Web, Worker, and reconciler before a file copy;
- restore verification still checks tenant-scoped row counts.

- [ ] **Step 5: Verify and commit**

Run:

```powershell
python -m pytest tests/acquisition/test_sqlite_runtime.py -q
python -m pytest tests/acquisition/test_workbench.py tests/acquisition/test_jobs.py -q
python -m ruff check app/extensions.py app/config.py tests/acquisition/test_sqlite_runtime.py
git diff --check
```

Commit:

```powershell
git add app/extensions.py app/config.py tests/acquisition/test_sqlite_runtime.py docs/RUNBOOK_BACKUP_RESTORE.md
git commit -m "fix(runtime): harden solo SQLite connections"
```

## Task 9: Record hosted blockers and run the complete non-browser gate

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/RUNBOOK_STAGING.md`
- Modify: `docs/PRODUCTION_READINESS_CHECKLIST.md`
- Create: `.autopilot/evidence/ACQ-1A-remediation/gate-results.md`

- [ ] **Step 1: Document the residual risks without pretending they are closed**

Add explicit hosted/public release blockers:

- reverse proxy and WSGI access logs must redact the path segment after `/verify-email/` and `/reset-password/`;
- `safe_event` protects structured application events only;
- StaticFetcher retains a DNS/connect TOCTOU residual risk;
- public SaaS requires the fetcher in an isolated worker with network-layer private-range egress denial;
- none of these claims is satisfied by local unit tests;
- SQLite remains one RQ Worker only; PostgreSQL is required before worker scale-out.

Do not add a fake redaction unit test unless this repository actually owns the selected access logger. Keep the readiness checkbox open until the deployment layer is configured and its emitted log line is tested.

- [ ] **Step 2: Run focused remediation tests**

```powershell
python -m pytest tests/acquisition -q
```

Expected: every acquisition test passes, including terminal retry, manual evidence, routes, `priority-v2`, workbench, and SQLite runtime.

- [ ] **Step 3: Run all static and non-browser gates**

```powershell
python -m ruff format .
python -m ruff check .
python -m ruff format --check .
python -m pytest --ignore=tests/test_playwright_launch_acceptance.py -q
git diff --check
```

Expected:

- Ruff lint: `All checks passed!`.
- Ruff format: all files already formatted after the formatting command.
- Non-browser suite: zero failed tests.
- Diff check: no output.

Do not run `tests/test_playwright_launch_acceptance.py`; it launches a browser and can overwrite legacy screenshot evidence.

- [ ] **Step 4: Run a disposable SQLite migration round trip**

Resolve a database path that is a direct child of the current worktree, then run:

```powershell
$remediationDb = Join-Path (Get-Location) '.tmp-acq-remediation.db'
$env:DATABASE_URL = "sqlite:///$($remediationDb -replace '\\','/')"
python -m alembic upgrade head
python -m alembic downgrade 0013_admin_auth_version
python -m alembic upgrade head
python -m alembic current
Remove-Item -LiteralPath $remediationDb -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$remediationDb-wal" -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$remediationDb-shm" -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL
```

Before each `Remove-Item`, confirm `$remediationDb` resolves inside the current worktree and has the exact filename `.tmp-acq-remediation.db`. Expected final revision: `0014_acquisition_core (head)`.

- [ ] **Step 5: Write evidence and commit documentation**

In `.autopilot/evidence/ACQ-1A-remediation/gate-results.md`, record:

- date, branch, and exact Head tested;
- command and pass/fail result for every gate;
- collected/passed test counts;
- migration final revision;
- explicit `NOT RUN` rows for browser, Docker runtime, PostgreSQL concurrency, and 30-company real sample;
- statement that no real external fetch, MiMo paid call, email send, or browser automation occurred.

Commit:

```powershell
git add docs/ARCHITECTURE.md docs/RUNBOOK_STAGING.md docs/PRODUCTION_READINESS_CHECKLIST.md .autopilot/evidence/ACQ-1A-remediation/gate-results.md
git commit -m "docs(acquisition): record remediation release gates"
```

- [ ] **Step 6: Final repository audit**

Run:

```powershell
git status --short
git log --oneline -10
rg -n "FIXME|XXX|HACK|priority-v1" app/modules/acquisition tests/acquisition docs/superpowers/plans/2026-08-02-phase-1a-audit-remediation.md
git diff c3293cc..HEAD --stat
```

Interpretation:

- `.autopilot/evidence/V2-05/v2-05-outreach-desktop.png` may remain modified and must remain unstaged.
- `priority-v1` may appear only in history-preservation tests, compatibility fallbacks that intentionally describe old rows, and documentation.
- No temporary implementation markers may remain in production paths.

## Completion checkpoint

This plan is complete only when Tasks 1-9 are checked, all listed non-browser gates pass, and the gate evidence file contains exact fresh results. Completion authorizes local Solo trial of manual URL and country-evidence workflows. It does not authorize a Phase 1A release checkpoint.

The release checkpoint remains blocked by four external gates:

1. Docker Compose runtime verification on a host with Docker Desktop/WSL2 or Linux Docker.
2. PostgreSQL migration plus concurrent promotion and multi-worker smoke.
3. A 30-company real positive/negative sample report with precision, coverage, elapsed time, and provider cost.
4. Hosted access-log redaction and isolated fetcher egress enforcement before any public SaaS exposure.
