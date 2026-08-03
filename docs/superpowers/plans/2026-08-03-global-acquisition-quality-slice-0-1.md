# Global Acquisition Quality Slice 0/1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repeatable, offline global-quality replay baseline and a single tenant-safe Mission business-result resolver that distinguishes useful partial output, reviewable output, no results, and genuine execution failure everywhere the user sees a Mission.

**Architecture:** Slice 0 is test-only/tooling infrastructure: a versioned manifest plus minimal redacted HTML fixtures are loaded by a standard-library replay tool, and the tool compares the frozen legacy output with human annotations without calling the network or changing production behavior. Slice 1 adds immutable business-result facts and a pure `BusinessResultResolver` in `states.py`; one ORM projection adapter loads tenant-scoped Mission/Candidate/Evidence/Job rows and every reconciler, route, HTMX fragment, workbench summary, notification, and audit path consumes the same resolved value. Mission `status` remains the execution lifecycle and no migration changes are made.

**Tech Stack:** Python 3.11, Flask, SQLAlchemy 2, Jinja/HTMX, pytest, Ruff, standard-library `dataclasses`, `json`, `argparse`, and `pathlib`

---

## Scope and file map

### Slice 0: offline baseline only

- Create `tools/acquisition_quality_replay.py`: load the versioned fixture manifest safely, validate each redacted source file, compare frozen legacy output with human annotations, calculate deterministic gap metrics, and expose a CLI.
- Create `tests/acquisition/test_quality_replay.py`: fixture-contract, traversal-safety, global-matrix, deterministic-report, and CLI tests.
- Create `tests/fixtures/acquisition/global_quality/cases.json`: manifest with legacy output and expected human labels.
- Create minimal redacted sources under `tests/fixtures/acquisition/global_quality/pages/`: Mexico, Brazil, Germany, United States, China-serving-Mexico, generic `.co`, global-company, sparse-page, chamber, directory, government, media, careers, and dealer counterexample fixtures.
- Do not import the replay tool from `app/`; do not add a runtime country/contact/entity parser; do not call MiMo or the public network.

### Slice 1: unified Mission business result

- Modify `app/modules/acquisition/states.py`: add immutable result facts, counts, result value, and the only `BusinessResultResolver` decision table while preserving human-terminal candidate protection.
- Create `app/modules/acquisition/mission_results.py`: tenant-scoped ORM projection adapter and recent-Mission read model; it is the only layer that converts ORM rows into resolver facts.
- Modify `app/modules/acquisition/repository.py`: add bounded recent-Mission and evidence-count projections, always requiring `tenant_id`.
- Modify `app/modules/jobs/repository.py`: add a tenant-scoped, job-type-bounded read used by the projection adapter.
- Modify `app/modules/acquisition/jobs.py`: use the resolver for terminal reconciliation, execution status, retrospective persistence, notification content/dedupe compatibility, notification archival, and idempotent audit.
- Modify `app/modules/acquisition/service.py`: replace candidate-list retrospective construction with resolver-backed backward-compatible payload data and archive terminal Mission notifications when a retry reopens work.
- Modify `app/modules/acquisition/workbench.py`: expose recent Mission summaries produced by the shared projection; retain existing unresolved-Job semantics.
- Modify `app/modules/acquisition/routes.py`: add the tenant-guarded Mission list, resolve Mission detail and HTMX status through the adapter, and pass one shared result to templates.
- Create `app/templates/acquisition/mission_list.html`: minimal read-only task list linking to each Mission.
- Modify `app/templates/acquisition/mission_detail.html`: show the resolved outcome, counts, reasons, and next action without hiding the execution status.
- Modify `app/templates/acquisition/_mission_status.html`: render active execution state or terminal business result from the same view object.
- Modify `app/templates/app/workbench.html` and `app/templates/app/_workbench_live.html`: add unified Mission/notification navigation and recent Mission outcomes without restructuring the sidebar.
- Modify acquisition templates with top navigation (`candidate_detail.html`, `mission_form.html`, `product_knowledge.html`, `notifications.html`) so “任务” and “通知” use the same canonical routes.
- Create `tests/acquisition/test_business_results.py`: pure resolver matrix and latest-logical-job tests.
- Modify `tests/acquisition/test_jobs.py`: reconciler, old failed Mission, structured retrospective, notification, audit, and idempotency tests.
- Modify `tests/acquisition/test_service.py`: retry archival compatibility and recovered-result tests.
- Modify `tests/acquisition/test_workbench.py`: tenant-scoped recent Mission results and workbench rendering tests.
- Modify `tests/acquisition/test_routes.py`: Mission list/detail/HTMX consistency, tenant isolation, and navigation tests.
- Do not modify `app/modules/acquisition/models.py` or any migration.

## Result contract fixed by this plan

The pure resolver returns exactly one code from `ready`, `needs_review`, `partial`, `no_results`, `failed`, or `cancelled`. It also returns a shared Chinese label, tone, action code/label, structured counts, and reason codes. Consumers must render those fields and must not maintain their own code-to-label mapping.

Resolution precedence is fixed:

1. `cancelled` when Mission execution is cancelled.
2. `partial` when the latest logical Job outcomes contain a failure and the Mission has at least one candidate or evidence item; legacy `status=failed` with material output is also `partial`.
3. `failed` when execution failed and there is no candidate or evidence, or the latest logical planning/search/infrastructure outcome failed with no material output.
4. `ready` when at least one candidate is `eligible`, `accepted`, or `promoted` and there is no unresolved latest Job failure.
5. `needs_review` when there is no ready candidate but at least one candidate is `discovered`, `verifying`, or `needs_evidence` and there is no unresolved latest Job failure.
6. `no_results` when terminal execution succeeded with zero candidates.

Only the latest terminal outcome for the same logical Job identity counts. Identities are `acquisition_plan + mission`, `web_discovery + mission + normalized country`, and candidate Job type + candidate ID. A later success therefore supersedes an earlier failure for the same identity, while another country or candidate does not.

The database execution status remains separate: when all relevant Jobs are terminal, unresolved latest Job failures persist Mission `status=failed`; otherwise Mission `status=completed`. Business `partial` is not added to the Mission status constraint.

### Task 1: Add the Slice 0 fixture contract and safe loader

**Files:**
- Create: `tools/acquisition_quality_replay.py`
- Create: `tests/acquisition/test_quality_replay.py`
- Create: `tests/fixtures/acquisition/global_quality/cases.json`
- Create: `tests/fixtures/acquisition/global_quality/pages/mx_official.html`

- [ ] **Step 1: Write the first failing loader test**

Create `tests/acquisition/test_quality_replay.py` with the exact first contract test:

```python
from __future__ import annotations

from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "acquisition" / "global_quality"


def test_load_replay_cases_reads_versioned_redacted_fixture() -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")

    assert suite.version == "acquisition-global-quality-v1"
    assert suite.cases[0].case_id == "mx-official-address"
    assert suite.cases[0].source_path.name == "mx_official.html"
    assert "Dirección oficial" in suite.cases[0].source_text
    assert suite.cases[0].expected["opportunity_country_code"] == "MX"
```

- [ ] **Step 2: Run the first test and confirm RED**

Run:

```powershell
python -m pytest tests/acquisition/test_quality_replay.py::test_load_replay_cases_reads_versioned_redacted_fixture -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'tools.acquisition_quality_replay'`.

- [ ] **Step 3: Add one minimal redacted fixture and manifest**

Create `pages/mx_official.html` containing only synthetic evidence:

```html
<!doctype html>
<html lang="es-MX">
<head><title>Distribuidor MX de ejemplo</title></head>
<body><main><h1>Refacciones para motocicleta</h1><p>Dirección oficial: Guadalajara, Jalisco, México.</p><a href="mailto:ventas@distribuidor.invalid">Ventas</a></main></body>
</html>
```

Create `cases.json` with the first case and fixed output shape:

```json
{
  "version": "acquisition-global-quality-v1",
  "cases": [
    {
      "id": "mx-official-address",
      "scenario": "Mexico ccTLD plus official address",
      "source": "pages/mx_official.html",
      "target_country_code": "MX",
      "legacy_output": {
        "hq_country_code": "",
        "opportunity_country_code": "",
        "country_resolution_status": "unknown",
        "contact_kinds": [],
        "entity_kind": "unknown"
      },
      "expected": {
        "hq_country_code": "MX",
        "opportunity_country_code": "MX",
        "country_resolution_status": "confirmed",
        "contact_kinds": ["email"],
        "entity_kind": "buyer_or_distributor"
      }
    }
  ]
}
```

- [ ] **Step 4: Implement the minimal safe loader**

Create `tools/acquisition_quality_replay.py` with immutable contracts, strict required keys, manifest-version validation, UTF-8 reads, and path containment:

```python
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUITE_VERSION = "acquisition-global-quality-v1"
OUTPUT_FIELDS = (
    "hq_country_code",
    "opportunity_country_code",
    "country_resolution_status",
    "contact_kinds",
    "entity_kind",
)


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    scenario: str
    target_country_code: str
    source_path: Path
    source_text: str
    legacy_output: dict[str, object]
    expected: dict[str, object]


@dataclass(frozen=True)
class ReplaySuite:
    version: str
    cases: tuple[ReplayCase, ...]


def _object(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def load_replay_cases(manifest_path: Path) -> ReplaySuite:
    manifest = manifest_path.resolve(strict=True)
    root = manifest.parent
    payload = _object(json.loads(manifest.read_text(encoding="utf-8")), name="manifest")
    if payload.get("version") != SUITE_VERSION:
        raise ValueError("unsupported replay fixture version")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("replay fixture cases are required")
    cases: list[ReplayCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        item = _object(raw, name="case")
        case_id = str(item.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError("replay case ids must be present and unique")
        seen.add(case_id)
        source = (root / str(item.get("source", ""))).resolve(strict=True)
        if root not in source.parents:
            raise ValueError("replay source must stay inside the fixture directory")
        legacy = _object(item.get("legacy_output"), name="legacy_output")
        expected = _object(item.get("expected"), name="expected")
        if set(legacy) != set(OUTPUT_FIELDS) or set(expected) != set(OUTPUT_FIELDS):
            raise ValueError("replay outputs do not match the fixed field contract")
        cases.append(
            ReplayCase(
                case_id=case_id,
                scenario=str(item.get("scenario", "")).strip(),
                target_country_code=str(item.get("target_country_code", "")).strip().upper(),
                source_path=source,
                source_text=source.read_text(encoding="utf-8"),
                legacy_output=dict(legacy),
                expected=dict(expected),
            )
        )
    return ReplaySuite(version=SUITE_VERSION, cases=tuple(cases))
```

- [ ] **Step 5: Add and run the traversal rejection test**

Use `tmp_path` to create a manifest whose source is `../outside.html`; assert `load_replay_cases` raises `ValueError` matching `stay inside`. Run the two loader tests and expect `2 passed`.

- [ ] **Step 6: Run Slice 0 focused lint and commit the contract**

Run:

```powershell
python -m pytest tests/acquisition/test_quality_replay.py -q
python -m ruff check tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py
python -m ruff format --check tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py
git diff --check
```

Expected: all commands pass. Stage only the files listed in this task and commit:

```powershell
git add tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py tests/fixtures/acquisition/global_quality/cases.json tests/fixtures/acquisition/global_quality/pages/mx_official.html
git commit -m "test(acquisition): add global quality replay contract"
```

### Task 2: Complete the global fixture matrix and deterministic comparison report

**Files:**
- Modify: `tools/acquisition_quality_replay.py`
- Modify: `tests/acquisition/test_quality_replay.py`
- Modify: `tests/fixtures/acquisition/global_quality/cases.json`
- Create: `tests/fixtures/acquisition/global_quality/pages/br_distributor.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/de_cross_border.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/us_distributor.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/cn_serves_mx.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/generic_co.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/global_branch.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/sparse_single_page.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/chamber.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/directory.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/government.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/media.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/careers.html`
- Create: `tests/fixtures/acquisition/global_quality/pages/dealer_counterexample.html`

- [ ] **Step 1: Write the failing matrix-coverage test**

Add:

```python
def test_fixture_matrix_covers_global_and_negative_cases() -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")
    case_ids = {case.case_id for case in suite.cases}

    assert {
        "mx-official-address",
        "br-local-phone",
        "de-eu-cross-border",
        "us-dot-com-address",
        "cn-headquarters-serves-mx",
        "generic-dot-co",
        "global-headquarters-opportunity-split",
        "sparse-single-page",
        "association-or-chamber",
        "directory-or-marketplace",
        "government",
        "media-or-article",
        "careers-page",
        "dealer-counterexample",
    } <= case_ids
    assert len(case_ids) == len(suite.cases)
    assert all(case.source_text.strip() for case in suite.cases)
    assert all("<script" not in case.source_text.casefold() for case in suite.cases)
```

Run it and confirm RED because only the Mexico case exists.

- [ ] **Step 2: Add the remaining minimal redacted pages and annotations**

Each page must be synthetic, under 1 KiB, and contain only the signals named by the case. The fixed evidence content is:

```text
br-local-phone: .com.br URL in manifest; lang=pt-BR; São Paulo address; tel:+55; distributor text.
de-eu-cross-border: .de URL; lang=de; Hamburg headquarters; explicit EU-wide sales; no target-country auto-confirm from language alone.
us-dot-com-address: .com URL; Austin, Texas, United States address; distributor text.
cn-headquarters-serves-mx: .com.cn URL; Shenzhen headquarters; explicit authorized Mexico distribution service; expected HQ=CN and opportunity=MX.
generic-dot-co: .co URL; neutral English copy; no Colombia address/phone; expected country unknown.
global-headquarters-opportunity-split: global .com; German headquarters and explicit Brazil sales office; expected HQ=DE and opportunity=BR.
sparse-single-page: generic URL; company name only; expected country unknown, contacts empty, entity unknown.
association-or-chamber: member-list copy; expected association_or_chamber.
directory-or-marketplace: multi-supplier listing copy; expected directory_or_marketplace.
government: public procurement authority copy; expected government.
media-or-article: dated editorial article copy; expected media_or_article.
careers-page: jobs/careers copy; expected unknown company evidence, not a verified buyer.
dealer-counterexample: real distributor copy whose company name contains “Directory”; expected buyer_or_distributor so name keywords cannot hard-delete it.
```

Set `legacy_output` to the frozen pre-Slice-2 state observed by the current system. Do not claim a current deterministic parser result that does not exist. Store human expectations separately and keep `.mx`, Spanish, Portuguese, or country words out of production code.

- [ ] **Step 3: Write the failing deterministic comparison test**

Add:

```python
def test_compare_legacy_to_expected_is_deterministic_and_field_level() -> None:
    from tools.acquisition_quality_replay import compare_legacy_to_expected, load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")
    first = compare_legacy_to_expected(suite)
    second = compare_legacy_to_expected(suite)

    assert first == second
    assert first["suite_version"] == "acquisition-global-quality-v1"
    assert first["case_count"] == 14
    assert first["field_count"] == 70
    mexico = next(item for item in first["cases"] if item["id"] == "mx-official-address")
    assert set(mexico["mismatches"]) == {
        "hq_country_code",
        "opportunity_country_code",
        "country_resolution_status",
        "contact_kinds",
        "entity_kind",
    }
    generic_co = next(item for item in first["cases"] if item["id"] == "generic-dot-co")
    assert "opportunity_country_code" not in generic_co["mismatches"]
```

Run it and confirm RED because `compare_legacy_to_expected` is missing.

- [ ] **Step 4: Implement field-level comparison and metrics**

Add:

```python
def compare_legacy_to_expected(suite: ReplaySuite) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    matched = 0
    for case in suite.cases:
        mismatches = [
            field
            for field in OUTPUT_FIELDS
            if case.legacy_output[field] != case.expected[field]
        ]
        matched += len(OUTPUT_FIELDS) - len(mismatches)
        rows.append(
            {
                "id": case.case_id,
                "scenario": case.scenario,
                "mismatches": mismatches,
                "legacy_output": case.legacy_output,
                "expected": case.expected,
            }
        )
    field_count = len(suite.cases) * len(OUTPUT_FIELDS)
    return {
        "suite_version": suite.version,
        "case_count": len(suite.cases),
        "field_count": field_count,
        "matched_fields": matched,
        "gap_fields": field_count - matched,
        "cases": rows,
    }
```

- [ ] **Step 5: Add a failing CLI test, then implement the CLI**

Use `subprocess.run` with `sys.executable`, the tool path, `--manifest`, and `--output`. Assert exit code 0, output JSON equals the function result, and stdout contains only `wrote replay report:` plus the destination—not fixture content or secrets.

Implement:

```python
def _main() -> int:
    parser = argparse.ArgumentParser(description="Compare frozen acquisition output with labels")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare_legacy_to_expected(load_replay_cases(args.manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote replay report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 6: Run and inspect the Slice 0 baseline**

Run:

```powershell
python -m pytest tests/acquisition/test_quality_replay.py -q
python tools/acquisition_quality_replay.py --manifest tests/fixtures/acquisition/global_quality/cases.json --output work/global-quality-slice-0-replay.json
python -m ruff check tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py
python -m ruff format --check tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py
git diff --check
```

Inspect `work/global-quality-slice-0-replay.json`. Confirm all 14 cases appear, `.co` remains country-unknown, China HQ and Mexico opportunity are separate, the dealer counterexample is not labelled a directory, and no source path escapes the fixture directory.

- [ ] **Step 7: Commit and review Slice 0 before Slice 1**

Stage only the Slice 0 files and commit:

```powershell
git add tools/acquisition_quality_replay.py tests/acquisition/test_quality_replay.py tests/fixtures/acquisition/global_quality
git commit -m "test(acquisition): establish global replay baseline"
```

Review the commit for network calls, copyrighted page copies, production imports, country-specific production logic, and secrets. Do not start Task 3 until the Slice 0 tests and review pass.

### Task 3: Add the pure BusinessResultResolver decision table

**Files:**
- Modify: `app/modules/acquisition/states.py`
- Create: `tests/acquisition/test_business_results.py`

- [ ] **Step 1: Write the first failing legacy-Mission result test**

Create:

```python
from __future__ import annotations

from app.modules.acquisition.states import (
    BusinessResultFacts,
    BusinessResultResolver,
    CandidateResultFact,
    JobResultFact,
)


def test_failed_mission_with_candidates_and_evidence_is_partial() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            execution_status="failed",
            candidates=(
                CandidateResultFact("candidate-1", "needs_evidence", evidence_count=2),
            ),
            jobs=(
                JobResultFact(
                    identity="website_verify:candidate:candidate-1",
                    job_type="website_verify",
                    status="failed",
                    error_code="source_unreachable",
                    outcome_order=1,
                ),
            ),
        )
    )

    assert result.code == "partial"
    assert result.label == "部分完成"
    assert result.tone == "warning"
    assert result.counts.discovered == 1
    assert result.counts.needs_review == 1
    assert result.counts.evidence == 2
    assert result.counts.verification_failed == 1
    assert result.action_code == "review_partial_results"
```

Run:

```powershell
python -m pytest tests/acquisition/test_business_results.py::test_failed_mission_with_candidates_and_evidence_is_partial -q
```

Expected: import fails because the result contracts do not exist.

- [ ] **Step 2: Add the immutable contracts and minimal partial branch**

Append to `states.py` without changing `HUMAN_TERMINAL_STATUSES`, `USABLE_CANDIDATE_STATUSES`, or `update_assessment_state_if_mutable`:

```python
from dataclasses import dataclass
from typing import Literal

BusinessResultCode = Literal[
    "ready", "needs_review", "partial", "no_results", "failed", "cancelled"
]


@dataclass(frozen=True)
class CandidateResultFact:
    candidate_id: str
    status: str
    evidence_count: int = 0


@dataclass(frozen=True)
class JobResultFact:
    identity: str
    job_type: str
    status: str
    error_code: str = ""
    outcome_order: int = 0


@dataclass(frozen=True)
class BusinessResultFacts:
    execution_status: str
    candidates: tuple[CandidateResultFact, ...] = ()
    jobs: tuple[JobResultFact, ...] = ()


@dataclass(frozen=True)
class BusinessResultCounts:
    discovered: int
    needs_review: int
    ready_to_review: int
    crm_ready: int
    excluded: int
    evidence: int
    failed_jobs: int
    verification_failed: int
    ai_analysis_failed: int


@dataclass(frozen=True)
class BusinessResult:
    code: BusinessResultCode
    label: str
    tone: str
    action_code: str
    action_label: str
    summary: str
    reason_codes: tuple[str, ...]
    counts: BusinessResultCounts
```

Implement `BusinessResultResolver.resolve` as a stateless classmethod. First dedupe Jobs by `identity`, keeping the greatest `outcome_order`; then calculate counts. The minimal first branch returns `partial` when `(latest failures or execution_status == "failed")` and `(candidate count or evidence count)`.

- [ ] **Step 3: Add the complete failing decision matrix**

Parametrize terminal facts and expected codes:

```python
@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (BusinessResultFacts("cancelled"), "cancelled"),
        (BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "eligible"),)), "ready"),
        (BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "accepted"),)), "ready"),
        (BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "needs_evidence"),)), "needs_review"),
        (BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "verifying"),)), "needs_review"),
        (BusinessResultFacts("completed"), "no_results"),
        (
            BusinessResultFacts(
                "failed",
                jobs=(JobResultFact("plan:m", "acquisition_plan", "failed", "provider_unavailable", 1),),
            ),
            "failed",
        ),
    ],
)
def test_business_result_matrix(facts: BusinessResultFacts, expected: str) -> None:
    assert BusinessResultResolver.resolve(facts).code == expected
```

Add focused assertions that `partial` dominates `ready` when a latest failure exists, `failed` never occurs with material evidence, and a rejected-only successfully completed Mission is not `ready`.

- [ ] **Step 4: Implement the complete table and shared presentation fields**

Use one private mapping inside `states.py`:

```python
_RESULT_PRESENTATION = {
    "ready": ("可审核", "success", "review_candidates", "审核候选"),
    "needs_review": ("待补证", "attention", "complete_evidence", "补充候选证据"),
    "partial": ("部分完成", "warning", "review_partial_results", "查看部分结果"),
    "no_results": ("未找到结果", "neutral", "refine_search", "调整条件后重试"),
    "failed": ("执行失败", "danger", "retry_mission", "检查原因并重试"),
    "cancelled": ("已取消", "neutral", "none", "无需操作"),
}
```

Build `summary` only from structured counts, for example `已发现 10；待补证 8；可审核 0；已排除 2；验证失败 1` with zero-valued failure clauses omitted. Build reason codes from stable codes such as `planning_failed`, `search_failed`, `verification_failed`, `ai_analysis_failed`, `legacy_failed_with_results`, and `completed_without_candidates`; never include raw exception text.

- [ ] **Step 5: Add latest-logical-outcome tests and implement them**

Add tests proving:

```python
def test_later_success_supersedes_failure_for_same_logical_identity() -> None:
    facts = BusinessResultFacts(
        "completed",
        jobs=(
            JobResultFact("web_discovery:m:MX", "web_discovery", "failed", "timeout", 1),
            JobResultFact("web_discovery:m:MX", "web_discovery", "succeeded", "", 2),
        ),
    )
    result = BusinessResultResolver.resolve(facts)
    assert result.code == "no_results"
    assert result.counts.failed_jobs == 0
```

Also prove a BR success does not hide an MX failure, and a later candidate-assess success does not hide another candidate's failure.

- [ ] **Step 6: Run resolver gates and commit**

```powershell
python -m pytest tests/acquisition/test_business_results.py -q
python -m pytest tests/acquisition/test_service.py -q
python -m ruff check app/modules/acquisition/states.py tests/acquisition/test_business_results.py
python -m ruff format --check app/modules/acquisition/states.py tests/acquisition/test_business_results.py
git diff --check
```

Expected: all pass and candidate human-terminal tests remain green. Commit:

```powershell
git add app/modules/acquisition/states.py tests/acquisition/test_business_results.py
git commit -m "feat(acquisition): add mission business result resolver"
```

### Task 4: Add one tenant-scoped ORM projection for the resolver

**Files:**
- Create: `app/modules/acquisition/mission_results.py`
- Modify: `app/modules/acquisition/repository.py`
- Modify: `app/modules/jobs/repository.py`
- Modify: `tests/acquisition/test_business_results.py`
- Modify: `tests/acquisition/test_repositories.py`

- [ ] **Step 1: Write the failing tenant-projection test**

Seed two tenants with Missions, candidates, evidence, and failed Jobs. Call `resolve_mission_result(session, own_mission, tenant_id="t1")`; assert its counts include only t1. Then call the same function with `tenant_id="t2"` and the t1 Mission and assert `ValueError("tenant_id mismatch")`.

The first positive assertion must be:

```python
assert result.counts == BusinessResultCounts(
    discovered=1,
    needs_review=1,
    ready_to_review=0,
    crm_ready=0,
    excluded=0,
    evidence=1,
    failed_jobs=1,
    verification_failed=1,
    ai_analysis_failed=0,
)
```

Run the test and confirm RED because `mission_results.py` is missing.

- [ ] **Step 2: Add bounded tenant-scoped repository projections**

Add these exact APIs:

```python
# MissionRepository
def list_recent(self, *, tenant_id: str, limit: int = 50) -> Sequence[AcquisitionMission]:
    tenant_id = _require_tenant(tenant_id)
    bounded = max(1, min(int(limit), 100))
    return list(
        self.session.scalars(
            select(AcquisitionMission)
            .where(AcquisitionMission.tenant_id == tenant_id)
            .order_by(AcquisitionMission.created_at.desc(), AcquisitionMission.id.desc())
            .limit(bounded)
        )
    )

# EvidenceRepository
def counts_by_candidate_ids(
    self, candidate_ids: Sequence[str], *, tenant_id: str
) -> dict[str, int]:
    tenant_id = _require_tenant(tenant_id)
    if not candidate_ids:
        return {}
    rows = self.session.execute(
        select(CandidateEvidence.candidate_id, func.count(CandidateEvidence.id))
        .where(
            CandidateEvidence.tenant_id == tenant_id,
            CandidateEvidence.candidate_id.in_(candidate_ids),
        )
        .group_by(CandidateEvidence.candidate_id)
    ).all()
    return {candidate_id: int(count) for candidate_id, count in rows}

# JobRepository
def list_by_types_for_tenant(
    self, job_types: Sequence[str], *, tenant_id: str
) -> Sequence[Job]:
    tenant_id = _require_tenant(tenant_id)
    if not job_types:
        return []
    return list(
        self.session.scalars(
            select(Job).where(Job.tenant_id == tenant_id, Job.job_type.in_(job_types))
        )
    )
```

Add repository tests for empty inputs, missing tenant IDs, and cross-tenant exclusion.

- [ ] **Step 3: Implement the only ORM-to-facts adapter**

Create `mission_results.py` with:

```python
@dataclass(frozen=True)
class MissionResultSummary:
    mission_id: str
    name: str
    execution_status: str
    result: BusinessResult | None
    target_url: str
    created_at: datetime


def resolve_mission_result(
    session: Session,
    mission: AcquisitionMission,
    *,
    tenant_id: str,
    candidates: Sequence[AcquisitionCandidate] | None = None,
    jobs: Sequence[Job] | None = None,
) -> BusinessResult:
    if not tenant_id or mission.tenant_id != tenant_id:
        raise ValueError("tenant_id mismatch")
    candidate_rows = tuple(
        candidates
        if candidates is not None
        else CandidateRepository(session).list_for_mission(mission.id, tenant_id=tenant_id)
    )
    if any(row.tenant_id != tenant_id or row.mission_id != mission.id for row in candidate_rows):
        raise ValueError("mission result rows crossed tenant or mission scope")
    candidate_ids = tuple(row.id for row in candidate_rows)
    evidence_counts = EvidenceRepository(session).counts_by_candidate_ids(
        candidate_ids, tenant_id=tenant_id
    )
    job_rows = tuple(
        jobs
        if jobs is not None
        else JobRepository(session).list_by_types_for_tenant(
            ACQUISITION_RESULT_JOB_TYPES, tenant_id=tenant_id
        )
    )
    facts = BusinessResultFacts(
        execution_status=mission.status,
        candidates=tuple(
            CandidateResultFact(row.id, row.status, evidence_counts.get(row.id, 0))
            for row in candidate_rows
        ),
        jobs=_mission_job_facts(mission.id, candidate_ids, job_rows, tenant_id=tenant_id),
    )
    return BusinessResultResolver.resolve(facts)
```

`_mission_job_facts` must parse payloads defensively, discard malformed/unrelated/cross-tenant rows, normalize discovery country codes, keep missing-country discoveries unique by Job ID, and derive a stable integer `outcome_order` from `(finished_at or updated_at or created_at, updated_at, created_at, id)` after sorting. It must never parse or expose `error_summary`.

- [ ] **Step 4: Add recent summary loading**

`list_mission_result_summaries(session, tenant_id, limit=50)` calls `MissionRepository.list_recent`, resolves only terminal Missions, and returns `result=None` for `draft`, `queued`, `running`, or `paused` so active lifecycle UI is not mislabeled as a terminal business outcome.

- [ ] **Step 5: Run projection/repository gates and commit**

```powershell
python -m pytest tests/acquisition/test_business_results.py tests/acquisition/test_repositories.py -q
python -m ruff check app/modules/acquisition/states.py app/modules/acquisition/mission_results.py app/modules/acquisition/repository.py app/modules/jobs/repository.py tests/acquisition/test_business_results.py tests/acquisition/test_repositories.py
python -m ruff format --check app/modules/acquisition/states.py app/modules/acquisition/mission_results.py app/modules/acquisition/repository.py app/modules/jobs/repository.py tests/acquisition/test_business_results.py tests/acquisition/test_repositories.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/mission_results.py app/modules/acquisition/repository.py app/modules/jobs/repository.py tests/acquisition/test_business_results.py tests/acquisition/test_repositories.py
git commit -m "feat(acquisition): project tenant mission results"
```

### Task 5: Reconcile execution status, retrospective, notifications, and audit from one result

**Files:**
- Modify: `app/modules/acquisition/jobs.py`
- Modify: `app/modules/acquisition/service.py`
- Modify: `tests/acquisition/test_jobs.py`
- Modify: `tests/acquisition/test_service.py`

- [ ] **Step 1: Change the existing failed-verification test to RED on the new semantics**

In `test_reconciler_failed_verification_marks_candidate_unusable`, require:

```python
retrospective = json.loads(mission.retrospective_json)
assert mission.status == "failed"
assert retrospective["business_result"]["code"] == "partial"
assert retrospective["business_result"]["counts"]["needs_review"] == 1
assert retrospective["business_result"]["counts"]["verification_failed"] == 1
assert notification.kind == "mission_partial"
assert notification.title == "找客户任务部分完成"
assert "已发现 1" in notification.body
assert "待补证 1" in notification.body
assert "查看部分结果" in notification.body
```

Run only this test and confirm RED because the current notification is `mission_failed` and no structured business result is stored.

- [ ] **Step 2: Make reconciler execution status independent of candidate usability**

After terminal candidate repair, call `resolve_mission_result` with the loaded Mission/candidates/Jobs. Set:

```python
next_status = "failed" if result.counts.failed_jobs else "completed"
```

Re-resolve once with that terminal execution status if it differs from the in-memory status, then persist `mission.status`, `finished_at`, and the result. Never add `partial`, `ready`, `needs_review`, or `no_results` to the ORM status.

- [ ] **Step 3: Replace retrospective construction with a result-backed compatibility payload**

Change `mission_retrospective_payload` to accept `BusinessResult` and return:

```python
return {
    "business_result": {
        "code": result.code,
        "label": result.label,
        "tone": result.tone,
        "action_code": result.action_code,
        "action_label": result.action_label,
        "summary": result.summary,
        "reason_codes": list(result.reason_codes),
        "counts": asdict(result.counts),
    },
    "discovered": result.counts.discovered,
    "eligible": result.counts.ready_to_review,
    "needs_evidence": result.counts.needs_review,
    "rejected": result.counts.excluded,
    "accepted": result.counts.crm_ready,
    "partial_failures": result.counts.failed_jobs,
    "partial_success": result.code == "partial",
    "candidate_count": result.counts.discovered,
}
```

Retain `rejected_by_reason` and `contactable` from the existing candidate projection for backward compatibility; do not rename or delete existing keys.

- [ ] **Step 4: Add a failing no-results versus failed test**

Seed two Missions:

- successful `acquisition_plan` and `web_discovery`, zero candidates → execution `completed`, business `no_results`;
- failed `acquisition_plan`, zero candidates/evidence → execution `failed`, business `failed`.

Assert their notifications are respectively `mission_completed`/`找客户任务未找到结果` and `mission_failed`/`找客户任务执行失败`.

- [ ] **Step 5: Generate notification fields only from the resolved result**

Use:

```python
kind = {
    "partial": "mission_partial",
    "failed": "mission_failed",
}.get(result.code, "mission_completed")
title = f"找客户任务{result.label}"
body = f"{mission.name}：{result.summary}。下一步：{result.action_label}。"
```

Keep the existing `mission-terminal:{mission.id}:{next_status}` dedupe keys so existing rows remain compatible. Archive the opposite legacy terminal key. When the current key already exists, update its kind/title/body/target, reactivate it as unread, and do not create another row.

- [ ] **Step 6: Add idempotent structured audit**

Before updating `retrospective_json`, capture its previous `business_result.code`. Add one audit event only when the terminal code or execution status changes:

```python
add_event(
    session,
    tenant_id=mission.tenant_id,
    actor_type="system",
    action="acquisition_mission.result_resolved",
    target_type="acquisition_mission",
    target_id=mission.id,
    safe_summary=(
        f"execution={next_status}; result={result.code}; "
        f"discovered={result.counts.discovered}; failed_jobs={result.counts.failed_jobs}"
    ),
)
```

Add a test that two reconciler calls create one notification and one `result_resolved` event, and that another tenant's rows cannot affect either.

- [ ] **Step 7: Preserve retry notification archival for both legacy terminal statuses**

In `retry_candidate_verification`, archive both `mission-terminal:{id}:failed` and `mission-terminal:{id}:completed` for the current tenant. Reopen `failed` Mission execution as today; do not demote a completed Mission that still has a usable candidate. Tests must assert other-tenant notifications remain unchanged.

- [ ] **Step 8: Run reconciler/service suites and commit**

```powershell
python -m pytest tests/acquisition/test_business_results.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py -q
python -m ruff check app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
python -m ruff format --check app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/jobs.py app/modules/acquisition/service.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py
git commit -m "fix(acquisition): reconcile mission business results"
```

### Task 6: Use the shared result in Mission detail and HTMX status

**Files:**
- Modify: `app/modules/acquisition/routes.py`
- Modify: `app/templates/acquisition/mission_detail.html`
- Modify: `app/templates/acquisition/_mission_status.html`
- Modify: `tests/acquisition/test_routes.py`

- [ ] **Step 1: Write the failing old-failed-Mission route test**

Seed a tenant Mission with `status=failed`, one `needs_evidence` candidate, one evidence row, and a failed verification Job. Request both the detail and `/status` routes and assert:

```python
assert detail.status_code == 200
assert fragment.status_code == 200
for html in (detail.get_data(as_text=True), fragment.get_data(as_text=True)):
    assert "部分完成" in html
    assert "执行状态：失败" in html
    assert "待补证 1" in html
    assert "执行失败" not in html.split("执行状态：失败", 1)[0]
```

Run it and confirm RED because both routes render only `mission.status`.

- [ ] **Step 2: Resolve once per route through the adapter**

In `_render_mission` and the HTMX status route call `resolve_mission_result` inside the existing tenant-scoped session and pass `business_result` to `_mission_status.html`. For active/draft Missions pass `None` as the business result and keep the execution label.

- [ ] **Step 3: Render the shared status and failure-attribution panel**

`_mission_status.html` must use `business_result.label`, `tone`, `summary`, and `action_label` without a local result-code map. It may keep one execution-status map for technical lifecycle. Terminal markup includes both:

```html
<span class="lf-badge lf-badge-{{ business_result.tone }}">{{ business_result.label }}</span>
<span class="lf-muted">执行状态：{{ execution_label }}</span>
<span class="lf-muted">{{ business_result.summary }}</span>
```

In `mission_detail.html`, add a compact terminal result panel with the same summary, reason-code-safe explanations, and action label. Do not make all negative states red; tone comes from the resolver.

- [ ] **Step 4: Add route tenant-isolation and consistency assertions**

Assert another tenant cannot access either route, and that detail, HTMX fragment, retrospective code, and notification kind all represent the same business code for `partial`, `no_results`, and `failed` fixtures.

- [ ] **Step 5: Run route gates and commit**

```powershell
python -m pytest tests/acquisition/test_routes.py tests/acquisition/test_jobs.py -q
python -m ruff check app/modules/acquisition/routes.py tests/acquisition/test_routes.py
python -m ruff format --check app/modules/acquisition/routes.py tests/acquisition/test_routes.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/routes.py app/templates/acquisition/mission_detail.html app/templates/acquisition/_mission_status.html tests/acquisition/test_routes.py
git commit -m "feat(acquisition): show unified mission outcomes"
```

### Task 7: Add the minimal task list, workbench summaries, and unified notification entry

**Files:**
- Modify: `app/modules/acquisition/workbench.py`
- Modify: `app/modules/acquisition/routes.py`
- Create: `app/templates/acquisition/mission_list.html`
- Modify: `app/templates/app/workbench.html`
- Modify: `app/templates/app/_workbench_live.html`
- Modify: `app/templates/acquisition/candidate_detail.html`
- Modify: `app/templates/acquisition/mission_detail.html`
- Modify: `app/templates/acquisition/mission_form.html`
- Modify: `app/templates/acquisition/product_knowledge.html`
- Modify: `app/templates/acquisition/notifications.html`
- Modify: `tests/acquisition/test_workbench.py`
- Modify: `tests/acquisition/test_routes.py`

- [ ] **Step 1: Write the failing tenant-scoped task-list test**

Seed own and other-tenant terminal Missions. Request `/acquisition/missions` and assert the own name/result/link are present, the other tenant name is absent, and active Missions show execution state rather than a terminal result.

Also assert anonymous access redirects to login.

- [ ] **Step 2: Add the minimal read-only route and template**

Add:

```python
@app.get("/acquisition/missions")
@tenant_required(app)
def acquisition_mission_list():
    tenant_id, _actor_id = _identity()
    with Session(get_engine(app)) as db_session:
        missions = list_mission_result_summaries(db_session, tenant_id=tenant_id, limit=50)
    return render_template("acquisition/mission_list.html", missions=missions)
```

The template contains name, created time, execution state for active tasks or shared business result for terminal tasks, `result.summary`, and a direct `/acquisition/missions/<id>` link. It is read-only; no bulk mutation or new filters.

- [ ] **Step 3: Write the failing workbench recent-result test**

Require `load_workbench(...).recent_missions` to contain at most five tenant-owned `MissionResultSummary` rows and the live partial to show the same `result.label`/`summary` as the task list. Ensure existing candidate, reply, Job failure, and next-action counts are unchanged.

- [ ] **Step 4: Add recent Mission summaries without changing Job semantics**

Add `recent_missions: tuple[MissionResultSummary, ...]` to `WorkbenchView` and fill it with `list_mission_result_summaries(db_session, tenant_id=tenant_id, limit=5)`. Keep `_unresolved_failures` and its candidate-terminal suppression rules unchanged.

Render a compact “最近任务” section in `_workbench_live.html`; terminal rows read resolver presentation fields, active rows read execution status. Every row links to the Mission.

- [ ] **Step 5: Add the canonical task and notification navigation links**

Across the listed templates, use exactly:

```html
<a href="/acquisition/missions">任务</a>
<a href="/notifications">通知{% if view is defined and view.notifications_unread is defined and view.notifications_unread %}（{{ view.notifications_unread }}）{% endif %}</a>
```

Do not add a new notification route or duplicate notification list logic. Do not rebuild the global sidebar.

- [ ] **Step 6: Run UI/route/workbench gates and commit**

```powershell
python -m pytest tests/acquisition/test_routes.py tests/acquisition/test_workbench.py -q
python -m ruff check app/modules/acquisition/routes.py app/modules/acquisition/workbench.py tests/acquisition/test_routes.py tests/acquisition/test_workbench.py
python -m ruff format --check app/modules/acquisition/routes.py app/modules/acquisition/workbench.py tests/acquisition/test_routes.py tests/acquisition/test_workbench.py
git diff --check
```

Commit:

```powershell
git add app/modules/acquisition/routes.py app/modules/acquisition/workbench.py app/templates/app/workbench.html app/templates/app/_workbench_live.html app/templates/acquisition tests/acquisition/test_routes.py tests/acquisition/test_workbench.py
git commit -m "feat(acquisition): add mission result list"
```

### Task 8: Verify Slice 0/1, replay a database copy, and write evidence

**Files:**
- Create: `.autopilot/evidence/ACQ-global-quality-p0/gate-results.md`
- Create: `.autopilot/evidence/ACQ-global-quality-p0/slice-0-replay.json`
- Create only test-backed corrections in files already listed above if inspection finds a defect.

- [ ] **Step 1: Run the focused Slice 0/1 suites**

```powershell
python -m pytest tests/acquisition/test_quality_replay.py tests/acquisition/test_business_results.py tests/acquisition/test_jobs.py tests/acquisition/test_service.py tests/acquisition/test_workbench.py tests/acquisition/test_routes.py -q
```

- [ ] **Step 2: Run the complete acquisition suite**

```powershell
python -m pytest tests/acquisition -q
```

- [ ] **Step 3: Run the proportionate full non-browser suite**

```powershell
python -m pytest --ignore=tests/test_playwright_launch_acceptance.py --ignore=tests/test_playwright_collection.py --ignore=tests/test_playwright_crm.py --ignore=tests/test_playwright_outreach_inbound.py -q
```

- [ ] **Step 4: Run static and diff gates**

```powershell
python -m ruff check .
python -m ruff format --check app tests tools run_worker.py
git diff --check
```

- [ ] **Step 5: Run migration roundtrip on a disposable database**

Create a task-specific directory under `C:\tmp`, point `DATABASE_URL` at its SQLite file, then run upgrade head → downgrade `0013_admin_auth_version` → upgrade head and confirm `0014_acquisition_core (head)`. Verify the resolved absolute temp path remains under the task directory before deleting it. Do not modify migrations 0001–0014.

- [ ] **Step 6: Generate and inspect the Slice 0 replay evidence**

```powershell
python tools/acquisition_quality_replay.py --manifest tests/fixtures/acquisition/global_quality/cases.json --output .autopilot/evidence/ACQ-global-quality-p0/slice-0-replay.json
```

Confirm the report is deterministic, contains all 14 cases, exposes baseline gaps instead of fabricated improvements, and contains no external page bodies or secrets.

- [ ] **Step 7: Replay the old Mexico Mission on a database copy**

Copy the known SQLite database into a fresh `C:\tmp\leadflow-global-quality-p0-*` directory. Never open the live database with a write-capable app. Against the copy, use a small task-local read-only inspection command or Flask test client to load Mission `93d10a606ecc47199037645554836107`, its tenant-scoped candidates/evidence/Jobs, and call the shared projection. Expected semantic result:

```text
execution_status=failed
business_result in {partial, needs_review}
discovered=10
needs_review=8
excluded=2
```

If the copied Job history contains unresolved latest failures, the exact expected business result is `partial`. Render the authenticated Mission detail against the copy and confirm detail plus HTMX fragment show the same result and no raw `None`.

- [ ] **Step 8: Start the local runtime conservatively**

Check only whether `MIMO_API_KEY`, `MIMO_BASE_URL`, `MIMO_MODEL`, `TENANT_SECRET_KEY`, and `REDIS_URL` exist; never print their values. Start one Redis/Memurai, one Web process, and exactly one RQ Worker. Check `/health/ready` and require HTTP 200 with database and Redis `ok` before asking the user to sign in. Do not invoke provider calls or automatic outreach.

- [ ] **Step 9: Perform a single-tab sequential UI smoke**

Use the in-app browser only after automated gates. In one tab, visit login, task list, old Mission detail, HTMX status, workbench, and notifications sequentially. Confirm result labels/counts/actions agree and colors distinguish failure, partial, review, and rejection without relying on color alone.

- [ ] **Step 10: Correct only demonstrated defects with RED→GREEN**

For every semantic mismatch, first add one focused failing test, run it to confirm RED, apply the smallest correction, and rerun the focused and complete acquisition suites. Do not tune country/contact/entity behavior; those are Slice 2+.

- [ ] **Step 11: Write the gate evidence**

Record exact commands, pass counts, migration revision, replay metrics, database-copy Mission output, `/health/ready`, and UI smoke observations in `.autopilot/evidence/ACQ-global-quality-p0/gate-results.md`. Do not include API keys, passwords, cookies, session tokens, raw MiMo responses, or live database contents.

- [ ] **Step 12: Final diff and scope audit**

Run:

```powershell
git status --short
git diff --stat 02de760..HEAD
git diff --check 02de760..HEAD
rg -n "\.mx|mexicana|Spanish|español" app
```

The production-code search must show no new country-special-case branch. Confirm no migration changed, no Slice 2–5 resolver/extractor was implemented, every new query is tenant-scoped, and no outreach action was added.

- [ ] **Step 13: Commit verification evidence and stop before push/merge**

```powershell
git add .autopilot/evidence/ACQ-global-quality-p0/gate-results.md .autopilot/evidence/ACQ-global-quality-p0/slice-0-replay.json
git commit -m "test(acquisition): verify global quality p0"
```

Invoke `verification-before-completion` and `requesting-code-review`. Present local results and the user test URL. Do not push, open/modify a PR, force-push, merge, or touch the live database without a new explicit user instruction.

## Plan self-review

- Spec coverage: Slice 0 global fixtures, offline legacy-to-label comparison, Slice 1 result codes/counts/reasons, old failed compatibility, no-results distinction, reconciler, detail, HTMX, workbench, notifications, audit, retry archival, task list, tenant scope, migration safety, database-copy replay, runtime readiness, and evidence are each assigned to a concrete task.
- Scope exclusions: no country resolver, contact extractor, entity classifier, delayed MiMo analysis, cross-Mission evidence reuse, feedback engine, automatic outreach, migration, or live-data rewrite is included.
- Placeholder scan: no unresolved marker remains; fixture evidence text, API signatures, first RED tests, expected failures, targeted commands, commits, and acceptance checks are explicit.
- Type consistency: `BusinessResultFacts`, `CandidateResultFact`, `JobResultFact`, `BusinessResultCounts`, `BusinessResult`, `BusinessResultResolver`, `resolve_mission_result`, and `MissionResultSummary` retain the same names and fields across all tasks.
- Safety: every ORM projection accepts `tenant_id`, Job payloads contain IDs only, malformed payloads are ignored safely, notification targets remain internal, audit summaries are bounded and structured, published migrations remain untouched, and no secret value is printed.
