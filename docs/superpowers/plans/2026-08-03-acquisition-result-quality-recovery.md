# Acquisition Result Quality Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every discovered acquisition candidate produces either a verified assessment, a bounded provisional assessment, or an explicit actionable failure without misleading scores or blank UI sections.

**Architecture:** Preserve the existing RQ stage graph and evidence tables. Add bounded recovery at the static-fetch and MiMo schema boundaries, centralize pure assessment computation so synchronous and background paths cannot diverge, and render decision-aware user summaries while retaining technical provenance behind disclosure.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy 2, RQ/Redis, Pydantic 2, httpx, BeautifulSoup, Jinja/HTMX, pytest, Ruff

---

## File map

- Create `app/modules/acquisition/assessment.py`: pure evidence selection, gate inputs, score inputs, provenance mode, and user-facing assessment explanation.
- Modify `app/integrations/web/sanitizer.py`: tolerate detached BeautifulSoup nodes.
- Modify `app/integrations/web/fetcher.py`: use the bounded 1 MiB default without changing SSRF protections.
- Modify `app/config.py`: expose the same 1 MiB default to the application factory.
- Modify `app/integrations/ai/mimo.py`: perform one safe schema-repair request.
- Modify `app/modules/acquisition/scoring.py`: represent unknown gate evidence and cap provisional bands.
- Modify `app/modules/acquisition/versions.py`: version evidence-only assessment provenance.
- Modify `app/modules/acquisition/jobs.py`: retain specific fetch failures, enqueue fallback assessment, and use centralized computation.
- Modify `app/modules/acquisition/service.py`: use the same centralized computation for manual and synchronous assessment.
- Modify `app/modules/acquisition/routes.py`: prepare localized decision-aware card fields.
- Modify `app/templates/acquisition/_candidate_card.html`: remove misleading AI confidence and rejected priority badges; explain empty states.
- Test `tests/acquisition/test_static_fetcher.py`.
- Test `tests/acquisition/test_mimo_provider.py`.
- Test `tests/acquisition/test_scoring.py`.
- Test `tests/acquisition/test_assessment.py`.
- Test `tests/acquisition/test_jobs.py`.
- Test `tests/acquisition/test_routes.py`.

### Task 1: Make static evidence fetching compatible with ordinary public pages

**Files:**
- Modify: `app/integrations/web/sanitizer.py`
- Modify: `app/integrations/web/fetcher.py`
- Modify: `app/config.py`
- Test: `tests/acquisition/test_static_fetcher.py`

- [ ] **Step 1: Write the detached-node regression test**

Add a test that reproduces the real nested-hidden-element crash:

```python
def test_sanitizer_skips_descendants_detached_with_hidden_parent():
    from app.integrations.web.sanitizer import sanitize_html

    snapshot = sanitize_html(
        '<div hidden><span style="display:none">discard</span></div>'
        '<p>Visible distributor</p>'
    )

    assert snapshot.text == "Visible distributor"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m pytest tests/acquisition/test_static_fetcher.py::test_sanitizer_skips_descendants_detached_with_hidden_parent -q
```

Expected: failure with the current BeautifulSoup `AttributeError`.

- [ ] **Step 3: Implement the minimal detached-node guard**

In the second BeautifulSoup traversal, ignore tags that were detached when an ancestor was decomposed:

```python
for node in soup.find_all(True):
    if node.attrs is None:
        continue
    style = re.sub(r"\s+", "", str(node.get("style", "")).lower())
```

- [ ] **Step 4: Verify GREEN for the sanitizer test**

Run the test from Step 2 and expect one pass.

- [ ] **Step 5: Write the default-size regression test**

Add a test that uses the default constructor and a body larger than 200 KiB but smaller than 1 MiB:

```python
def test_fetcher_default_accepts_modern_page_below_one_mebibyte():
    from app.integrations.web.fetcher import StaticFetcher

    body = b"<p>dealer</p>" + (b" " * (256 * 1024))
    fetcher = StaticFetcher(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=body,
            )
        ),
        resolver=lambda _host: ["93.184.216.34"],
    )

    result = fetcher.fetch("https://example.com")
    assert "dealer" in result.text
```

- [ ] **Step 6: Run the size test and verify RED**

Expected: `response_too_large` under the current 200 KiB default.

- [ ] **Step 7: Raise only the bounded default**

Set the default in both `StaticFetcher` and application config:

```python
DEFAULT_FETCH_MAX_BYTES = 1024 * 1024
```

Keep caller-provided limits, 20,000-character sanitized output, private-address blocking, redirect validation, DNS verification, and content-type checks unchanged.

- [ ] **Step 8: Run the complete fetcher suite**

Run:

```powershell
python -m pytest tests/acquisition/test_static_fetcher.py -q
```

Expected: all fetcher and SSRF regression tests pass.

- [ ] **Step 9: Commit Task 1**

Stage only the four files and commit:

```powershell
git commit -m "fix(acquisition): harden static evidence fetching"
```

### Task 2: Repair one invalid MiMo structured response safely

**Files:**
- Modify: `app/integrations/ai/mimo.py`
- Test: `tests/acquisition/test_mimo_provider.py`

- [ ] **Step 1: Write the successful repair test**

Use a sequential fake response source:

```python
def test_invalid_structured_output_gets_one_schema_repair_attempt():
    from app.integrations.ai.mimo import MiMoProvider

    outputs = iter([
        '{"company_name":"Motozoon"}',
        (
            '{"company_name":"Motozoon","canonical_domain":"motozoon.mx",'
            '"hq_country_code":"MX","opportunity_country_code":"MX",'
            '"buyer_type":"distributor","product_terms":["motorcycle parts"],'
            '"contact_paths":[],"observed_claims":[],"inferences":[],"unknowns":[]}'
        ),
    ])
    calls = []
    responses = SimpleNamespace(
        create=lambda **kwargs: (
            calls.append(kwargs),
            SimpleNamespace(output_text=next(outputs)),
        )[1]
    )
    provider = MiMoProvider(
        client=SimpleNamespace(responses=responses),
        model="mimo-v2.5",
    )
    snapshot = SimpleNamespace(
        final_url="https://motozoon.mx/", title="Motozoon", text="wholesale parts"
    )

    result = provider.extract(snapshot)

    assert result.company_name == "Motozoon"
    assert len(calls) == 2
    assert "previous response" in calls[1]["instructions"].lower()
```

- [ ] **Step 2: Run the repair test and verify RED**

Expected: the first invalid response immediately raises `ProviderResponseError`.

- [ ] **Step 3: Write the safe terminal-failure test**

Return two malformed responses, then assert two calls, error code `invalid_response`, and absence of the raw sentinel value from the exception and captured logs.

- [ ] **Step 4: Implement one bounded validation repair**

Split validation into a helper that returns safe validation locations:

```python
def _validate_json(output_text: str, schema: type[_Schema]) -> _Schema:
    return schema.model_validate_json(output_text)

def _safe_validation_paths(exc: ValidationError) -> str:
    paths = sorted({".".join(map(str, item["loc"])) or "root" for item in exc.errors()})
    return ", ".join(paths[:10]) or "root"
```

On the first schema failure, call `_request_with_retry` once more with the same sanitized input and instructions extended by safe paths. Never include the invalid output or rejected values. The second schema failure raises the existing safe `ProviderResponseError`.

- [ ] **Step 5: Run the complete MiMo provider suite**

Run:

```powershell
python -m pytest tests/acquisition/test_mimo_provider.py -q
```

- [ ] **Step 6: Commit Task 2**

```powershell
git commit -m "fix(acquisition): repair invalid mimo schema once"
```

### Task 3: Centralize evidence-aware assessment and unknown semantics

**Files:**
- Create: `app/modules/acquisition/assessment.py`
- Modify: `app/modules/acquisition/scoring.py`
- Modify: `app/modules/acquisition/versions.py`
- Test: `tests/acquisition/test_scoring.py`
- Create: `tests/acquisition/test_assessment.py`

- [ ] **Step 1: Write gate tests for genuinely unknown evidence**

Add tests showing that `None` means unknown while `False` means confirmed negative:

```python
def test_unknown_product_and_contact_require_evidence_instead_of_rejection():
    result = evaluate_gate(
        EligibilityFacts(
            country_status="unknown",
            buyer_type_match=None,
            excluded_business=False,
            independent_identity=True,
            product_evidence=None,
            contact_path=None,
        )
    )
    assert result.disposition == "needs_evidence"
    assert "product_evidence_unknown" in result.reason_codes
    assert "contact_path_unknown" in result.reason_codes

def test_confirmed_missing_product_evidence_is_rejected():
    facts = EligibilityFacts(
        country_status="confirmed",
        buyer_type_match=True,
        excluded_business=False,
        independent_identity=True,
        product_evidence=False,
        contact_path=True,
    )
    assert evaluate_gate(facts).disposition == "rejected"
```

- [ ] **Step 2: Run the gate tests and verify RED**

Expected: current bool-only policy rejects unknown values.

- [ ] **Step 3: Implement tri-state gate inputs**

Change `buyer_type_match`, `product_evidence`, and `contact_path` to `bool | None`. Reject only explicit `False`; collect safe unknown reason codes for `None`; return `needs_evidence` when unknowns remain.

- [ ] **Step 4: Change provisional band behavior test-first**

Update the existing provisional test to require B and add evidence-only mode:

```python
assert result.priority_mode == "fit_quality_provisional_v1"
assert result.priority_band == "B"
```

Add an input with no fit or intent but known quality and assert:

```python
assert result.priority_mode == "evidence_only_provisional_v1"
assert result.priority_band == "B"
```

Run and verify failure before implementation.

- [ ] **Step 5: Implement the evidence-only priority mode**

Extend `PriorityMode` and choose it when `fit is None` and `intent is None`. `_band` returns at most B for either provisional mode; full mode retains S/A/B/C behavior.

- [ ] **Step 6: Write pure assessment computation tests**

Create ORM objects without a database and assert:

- unverified Trust D search evidence creates evidence-only provisional computation;
- valid Trust A evidence plus structured facts creates fit-quality computation;
- unreachable error evidence is excluded from trust scoring;
- duplicated evidence for the same canonical URL counts as one independent source;
- a mismatched buyer type remains a hard rejection;
- explanations contain an actionable reason and never chain-of-thought.

- [ ] **Step 7: Implement `assessment.py`**

Expose a pure result type and function:

```python
def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def explain_assessment(gate: GateResult, *, extraction_complete: bool) -> str:
    if not extraction_complete:
        return "当前为临时评估；官网验证或结构化分析尚未完成，请重新验证。"
    if gate.disposition == "rejected":
        labels = {
            "wrong_country": "公开证据显示目标国家不匹配。",
            "wrong_buyer_type": "公开证据显示该企业不是目标买家类型。",
            "excluded_business": "公开证据命中了排除业务类型。",
            "no_independent_identity": "尚未确认独立企业身份。",
        }
        return labels.get(gate.reason_codes[0], "公开证据未通过当前资格门禁。")
    if gate.disposition == "needs_evidence":
        return "基础信息具有相关性，但国家、买家角色或联系方式仍需补充证据。"
    return "公开证据符合当前目标市场和买家类型。"


@dataclass(frozen=True)
class AssessmentComputation:
    gate: GateResult
    score_input: ScoreInput
    score: ScoreResult
    evidence_bundle_hash: str
    prompt_version: str
    model_provider: str
    model_id: str
    explanation: str
    extraction_complete: bool

def compute_candidate_assessment(
    candidate: AcquisitionCandidate,
    mission: AcquisitionMission,
    evidence_items: Sequence[CandidateEvidence],
    *,
    mimo_model_id: str,
) -> AssessmentComputation:
    target = _json_object(mission.target_profile_json)
    observed = _json_object(candidate.observed_facts_json)
    contact = _json_object(candidate.contact_json)
    usable = tuple(
        item
        for item in evidence_items
        if item.validation_status in {"valid", "unverified"}
    )
    extraction_complete = isinstance(observed, dict) and {
        "buyer_type",
        "product_terms",
        "claims",
    }.issubset(observed)
    buyer_type = str(observed.get("buyer_type", "")).lower()
    expected_buyers = {str(item).lower() for item in target.get("buyer_types", [])}
    buyer_match = None if not buyer_type else not expected_buyers or buyer_type in expected_buyers
    product_terms = [str(item) for item in observed.get("product_terms", [])]
    claims = list(observed.get("claims", []))
    contact_paths = [str(item) for item in contact.get("paths", [])]
    country_codes = {str(item).upper() for item in target.get("country_codes", [])}
    gate_country = candidate.country_resolution_status
    if (
        gate_country == "confirmed"
        and country_codes
        and candidate.opportunity_country_code not in country_codes
    ):
        gate_country = "mismatch"
    combined = " ".join(
        [candidate.company_name, buyer_type, *product_terms, json.dumps(claims)]
    ).lower()
    gate = evaluate_gate(
        EligibilityFacts(
            country_status=gate_country,
            buyer_type_match=buyer_match,
            excluded_business=any(
                str(term).lower() in combined for term in target.get("exclude_terms", [])
            ),
            independent_identity=bool(candidate.company_name and candidate.domain),
            product_evidence=True if product_terms or claims else None,
            contact_path=True if contact_paths else None,
        )
    )
    trust_values = {"A": 100, "B": 80, "C": 60, "D": 40, "E": 20}
    unique_sources = {item.canonical_url for item in usable if item.canonical_url}
    best_trust = max((trust_values.get(item.trust_tier, 0) for item in usable), default=0)
    score_input = ScoreInput(
        product_relevance=85 if product_terms else None,
        buyer_role=85 if buyer_match is True else (0 if buyer_match is False else None),
        country_match=100 if gate_country == "confirmed" else (0 if gate_country == "mismatch" else None),
        company_size=None,
        industry_match=70 if product_terms else None,
        direct_purchase=None,
        recent_activity=None,
        competitor_signal=None,
        signal_recency=None,
        identity_quality=90 if candidate.company_name and candidate.domain else None,
        source_trust=best_trust or None,
        contactability=80 if contact_paths else None,
        independent_evidence=80 if len(unique_sources) >= 2 else (50 if unique_sources else None),
        data_recency=90 if usable else None,
    )
    score = score_candidate(score_input)
    bundle_hash = hashlib.sha256(
        canonical_json(
            sorted(
                (item.canonical_url, item.content_hash, item.validation_status)
                for item in usable
            )
        ).encode("utf-8")
    ).hexdigest()
    return AssessmentComputation(
        gate=gate,
        score_input=score_input,
        score=score,
        evidence_bundle_hash=bundle_hash,
        prompt_version=(MIMO_EXTRACT_PROMPT_VERSION if extraction_complete else EVIDENCE_ONLY_PROMPT_VERSION),
        model_provider="mimo" if extraction_complete else "deterministic",
        model_id=mimo_model_id if extraction_complete else "evidence-only-v1",
        explanation=explain_assessment(gate, extraction_complete=extraction_complete),
        extraction_complete=extraction_complete,
    )
```

The function includes only evidence with `valid` or `unverified` validation status, distinguishes absent structured extraction from negative evidence, hashes the selected bundle, and returns deterministic localized explanations.

Add `EVIDENCE_ONLY_PROMPT_VERSION = "evidence-only-v1"` to `versions.py`.

- [ ] **Step 8: Run scoring and assessment suites**

```powershell
python -m pytest tests/acquisition/test_scoring.py tests/acquisition/test_assessment.py -q
```

- [ ] **Step 9: Commit Task 3**

```powershell
git commit -m "feat(acquisition): add provisional evidence assessment"
```

### Task 4: Degrade failed verification into a persisted provisional assessment

**Files:**
- Modify: `app/modules/acquisition/jobs.py`
- Modify: `app/modules/acquisition/service.py`
- Test: `tests/acquisition/test_jobs.py`
- Test: `tests/acquisition/test_service.py`

- [ ] **Step 1: Write the fetch-failure fallback test**

Arrange a discovered candidate with Trust D search evidence, make `StaticFetcher.fetch` raise `FetchError("response_too_large", "Evidence page exceeds size limit")`, and capture queued jobs. Assert:

```python
with pytest.raises(AcquisitionJobError) as caught:
    handle_website_verify(app, verify_job, {"candidate_id": candidate_id})

assert caught.value.code == "response_too_large"
assert any(item["job_type"] == "candidate_assess" for item in queued)
```

Also assert the stored fetch-error evidence contains a safe specific explanation and no exception body.

- [ ] **Step 2: Run the fallback test and verify RED**

Expected: current code maps the error to `source_unreachable` and does not enqueue assessment.

- [ ] **Step 3: Write the extraction-failure fallback test**

Return a valid static snapshot, make the provider raise `ProviderResponseError`, and assert that official Trust A evidence remains and `candidate_assess` is queued once.

- [ ] **Step 4: Implement the idempotent assessment enqueue helper**

Add a helper that checks `JobRepository.has_active_for_candidate` before calling `create_and_enqueue`. Use it after successful extraction and before re-raising either fetch or provider extraction failures.

Preserve exact `FetchError.code` and `safe_summary` in `AcquisitionJobError`. Store a code-specific safe evidence excerpt.

- [ ] **Step 5: Write background assessment persistence tests**

Assert that a search-evidence-only candidate receives:

- one `CandidateAssessment` with evidence-only provenance;
- status `needs_evidence`;
- a B-or-lower provisional band;
- nonzero evidence quality when usable search evidence exists;
- no promotion or eligibility;
- idempotent repeated assessment for the same evidence bundle.

Also assert the verified path updates the legacy `ai_confidence` field consistently for backward compatibility even though the primary UI no longer labels it AI confidence.

- [ ] **Step 6: Replace duplicated job computation with the centralized function**

`handle_candidate_assess` loads candidate, mission, and evidence, calls `compute_candidate_assessment`, persists the versioned row if absent, copies score fields to the candidate, and updates mutable workflow state using the computed gate.

- [ ] **Step 7: Align the synchronous service path**

Replace the duplicate score/gate construction inside `_assess_candidate_in_session` with the same computation. Preserve caller-supplied manual/MiMo provenance where applicable and existing human-terminal state protection.

- [ ] **Step 8: Run job and service suites**

```powershell
python -m pytest tests/acquisition/test_jobs.py tests/acquisition/test_service.py -q
```

- [ ] **Step 9: Commit Task 4**

```powershell
git commit -m "fix(acquisition): persist verification fallback assessments"
```

### Task 5: Make candidate cards decision-aware and actionable

**Files:**
- Modify: `app/modules/acquisition/routes.py`
- Modify: `app/templates/acquisition/_candidate_card.html`
- Test: `tests/acquisition/test_routes.py`

- [ ] **Step 1: Write rejected-priority UI test**

Seed a rejected candidate with an A assessment and assert the primary layer contains the rejected decision but not `A` priority. The technical section may retain the raw score.

- [ ] **Step 2: Write empty-state UI tests**

Cover three states:

- evidence-only provisional assessment explains that official verification or extraction is pending;
- absent intent displays “未观察到采购意向信号” rather than `None`;
- no model inference displays an evidence-based conclusion rather than an empty “暂无推断”.

Assert the primary and expanded user sections do not contain raw `None` or an internal priority-mode name.

- [ ] **Step 3: Run the route tests and verify RED**

Run the new tests individually and confirm they fail against the existing card.

- [ ] **Step 4: Add a presentation view model**

Extend `_candidate_view` with:

```python
decision_label = {
    "eligible": "符合目标",
    "needs_evidence": "需要补充证据",
    "rejected": "已拒绝",
    "accepted": "已接受",
    "promoted": "已加入 CRM",
}.get(candidate.status, "处理中")
display_priority = (
    None
    if candidate.status == "rejected" or not assessment
    else candidate.priority_band or None
)
score_labels = {
    "fit_score": "匹配度",
    "intent_score": "采购意向",
    "data_quality_score": "证据质量",
    "priority_score": "综合优先级",
    "signal_coverage": "信号覆盖",
}
score_rows = [
    (label, "未观察到" if breakdown.get(key) is None else breakdown[key])
    for key, label in score_labels.items()
    if key in breakdown
]
analysis_conclusion = reason or "当前结论仅依据已保存的公开证据。"
processing_note = (
    "官网验证或结构化分析尚未完成；当前为临时评估，可重新验证。"
    if priority_mode == "evidence_only_provisional_v1"
    else (
        "尚未观察到采购意向信号；当前优先级仅依据匹配度和证据质量。"
        if priority_mode == "fit_quality_provisional_v1"
        else ""
    )
)
view.update(
    decision_label=decision_label,
    display_priority=display_priority,
    score_rows=score_rows,
    analysis_conclusion=analysis_conclusion,
    processing_note=processing_note,
    is_provisional=priority_mode != "full_v1",
)
```

Translate score keys and missing intent in Python so Jinja never renders raw `None` values.

- [ ] **Step 5: Update the candidate card**

- rejected candidates show only the rejected decision in the primary badge;
- eligible/needs-evidence candidates may show verified or provisional priority;
- remove primary `AI confidence`;
- label quality as evidence/data quality;
- replace `AI 推断` with `AI 分析结论`;
- render a reason plus next action for pending verification/extraction;
- retain model IDs, versions, hashes, and raw modes only inside technical details.

- [ ] **Step 6: Run the complete acquisition route suite**

```powershell
python -m pytest tests/acquisition/test_routes.py -q
```

- [ ] **Step 7: Commit Task 5**

```powershell
git commit -m "fix(acquisition): clarify candidate assessment output"
```

### Task 6: Verify the full system and inspect actual output

**Files:**
- Update only if output inspection reveals a test-backed defect in files already listed above.
- Evidence: `.autopilot/evidence/ACQ-1A-result-quality/`

- [ ] **Step 1: Run targeted acquisition tests**

```powershell
python -m pytest tests/acquisition -q
```

- [ ] **Step 2: Run the complete non-browser suite**

```powershell
python -m pytest --ignore=tests/test_playwright_launch_acceptance.py --ignore=tests/test_playwright_collection.py --ignore=tests/test_playwright_crm.py --ignore=tests/test_playwright_outreach_inbound.py -q
```

- [ ] **Step 3: Run static gates**

```powershell
python -m ruff check .
python -m ruff format --check app tests run_worker.py
git diff --check
```

- [ ] **Step 4: Run migration roundtrip smoke on a disposable SQLite database**

Upgrade to head, downgrade to `0013_admin_auth_version`, upgrade to head, and assert current is `0014_acquisition_core (head)`. Delete only the verified disposable database afterward.

- [ ] **Step 5: Replay the affected Mission on a database copy**

Copy `leadflow-v2-dev.db` to a task-specific temporary directory. Point `DATABASE_URL` at the copy, run provisional assessment for the eight incomplete candidates, and render the authenticated Mission detail using Flask’s test client. Do not modify the live database in this step.

Capture a structured report with, per candidate:

- final decision;
- display priority;
- evidence quality and coverage;
- analysis conclusion;
- explicit missing-data reason;
- next action.

- [ ] **Step 6: Inspect semantic output, not only HTTP status**

Fail the acceptance check if any card:

- contains raw `None`;
- shows A/B/S as the primary state for a rejected candidate;
- has an unexplained blank conclusion or score;
- treats unverified search evidence as confirmed fact;
- lacks a retry or evidence-completion action when provisional.

- [ ] **Step 7: Tune only defects demonstrated by output inspection**

For each defect, add a focused failing regression test, watch it fail, implement one minimal correction, and rerun the focused plus targeted suites. Do not adjust scoring weights solely to make the sample look better.

- [ ] **Step 8: Restart the local app on the verified code and inspect the live route**

Keep one web process, one RQ worker, and one reconciler. Verify `/health/ready`, authenticate with a local test client, request the affected Mission route, and compare its semantic output with the database-copy report. Browser automation is optional and must remain single-command because the local browser has previously become unstable under parallel commands.

- [ ] **Step 9: Write evidence and commit any final test-backed tuning**

Record commands, counts, and the semantic output audit under `.autopilot/evidence/ACQ-1A-result-quality/`. Never include API keys, cookies, raw provider bodies, or private exception detail.

If tuning changed code, commit:

```powershell
git commit -m "test(acquisition): validate result quality recovery"
```

- [ ] **Step 10: Finish the branch**

Invoke `finishing-a-development-branch`, rerun its required verification on the branch, and present merge/push options. Do not push or merge without the user’s selected option.
