from __future__ import annotations

import pytest

from app.modules.acquisition.states import (
    BusinessResultCounts,
    BusinessResultFacts,
    BusinessResultResolver,
    CandidateResultFact,
    JobResultFact,
)


def test_failed_mission_with_candidates_and_evidence_is_partial() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            execution_status="failed",
            candidates=(CandidateResultFact("candidate-1", "needs_evidence", evidence_count=2),),
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


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        (BusinessResultFacts("cancelled"), "cancelled"),
        (
            BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "eligible"),)),
            "ready",
        ),
        (
            BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "accepted"),)),
            "ready",
        ),
        (
            BusinessResultFacts(
                "completed", candidates=(CandidateResultFact("c", "needs_evidence"),)
            ),
            "needs_review",
        ),
        (
            BusinessResultFacts("completed", candidates=(CandidateResultFact("c", "verifying"),)),
            "needs_review",
        ),
        (BusinessResultFacts("completed"), "no_results"),
        (
            BusinessResultFacts(
                "failed",
                jobs=(
                    JobResultFact(
                        "plan:m",
                        "acquisition_plan",
                        "failed",
                        "provider_unavailable",
                        1,
                    ),
                ),
            ),
            "failed",
        ),
    ],
)
def test_business_result_matrix(facts: BusinessResultFacts, expected: str) -> None:
    assert BusinessResultResolver.resolve(facts).code == expected


def test_partial_dominates_ready_when_a_latest_failure_exists() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "failed",
            candidates=(CandidateResultFact("c", "eligible", evidence_count=1),),
            jobs=(JobResultFact("verify:c", "website_verify", "failed", "timeout", 1),),
        )
    )

    assert result.code == "partial"
    assert result.counts.ready_to_review == 1


def test_legacy_failed_mission_with_material_is_never_failed() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "failed",
            candidates=(CandidateResultFact("c", "needs_evidence", evidence_count=1),),
        )
    )

    assert result.code == "partial"
    assert result.reason_codes == ("legacy_failed_with_results",)


def test_rejected_only_completed_mission_is_not_ready() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "completed",
            candidates=(CandidateResultFact("c", "rejected", evidence_count=1),),
        )
    )

    assert result.code == "no_results"
    assert result.counts.excluded == 1
    assert result.reason_codes == ("all_candidates_excluded",)


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


@pytest.mark.parametrize("retry_status", ["queued", "running", "retrying"])
def test_non_terminal_retry_does_not_supersede_latest_terminal_failure(
    retry_status: str,
) -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "completed",
            candidates=(CandidateResultFact("c", "eligible", evidence_count=1),),
            jobs=(
                JobResultFact("verify:c", "website_verify", "failed", "timeout", 1),
                JobResultFact("verify:c", "website_verify", retry_status, "", 2),
            ),
        )
    )

    assert result.code == "partial"
    assert result.counts.failed_jobs == 1


def test_cancelled_terminal_retry_supersedes_prior_failure() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "completed",
            candidates=(CandidateResultFact("c", "eligible", evidence_count=1),),
            jobs=(
                JobResultFact("verify:c", "website_verify", "failed", "timeout", 1),
                JobResultFact("verify:c", "website_verify", "cancelled", "", 2),
            ),
        )
    )

    assert result.code == "ready"
    assert result.counts.failed_jobs == 0


def test_success_for_another_identity_does_not_hide_failure() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "failed",
            jobs=(
                JobResultFact("web_discovery:m:MX", "web_discovery", "failed", "timeout", 1),
                JobResultFact("web_discovery:m:BR", "web_discovery", "succeeded", "", 2),
            ),
        )
    )

    assert result.code == "failed"
    assert result.counts.failed_jobs == 1
    assert "search_failed" in result.reason_codes


def test_assessment_success_for_another_candidate_does_not_hide_failure() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "failed",
            jobs=(
                JobResultFact("candidate_assess:c1", "candidate_assess", "failed", "timeout", 1),
                JobResultFact("candidate_assess:c2", "candidate_assess", "succeeded", "", 2),
            ),
        )
    )

    assert result.code == "failed"
    assert result.counts.ai_analysis_failed == 1
    assert "ai_analysis_failed" in result.reason_codes


def test_summary_uses_only_structured_counts() -> None:
    result = BusinessResultResolver.resolve(
        BusinessResultFacts(
            "failed",
            candidates=(CandidateResultFact("c", "needs_evidence", evidence_count=2),),
            jobs=(JobResultFact("verify:c", "website_verify", "failed", "secret raw error", 1),),
        )
    )

    assert "已发现 1" in result.summary
    assert "待补证 1" in result.summary
    assert "验证失败 1" in result.summary
    assert "secret raw error" not in result.summary


def test_mission_result_projection_is_tenant_scoped(
    acquisition_app, seed_acquisition_mission
) -> None:
    import json

    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.mission_results import resolve_mission_result
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        CandidateEvidence,
    )
    from app.modules.jobs.models import Job

    own_mission_id = seed_acquisition_mission(tenant_id="t1", suffix="result-own")
    other_mission_id = seed_acquisition_mission(tenant_id="t2", suffix="result-other")
    with Session(get_engine(acquisition_app)) as session:
        own_mission = session.get(AcquisitionMission, own_mission_id)
        other_mission = session.get(AcquisitionMission, other_mission_id)
        assert own_mission is not None
        assert other_mission is not None
        own_mission.status = "failed"
        other_mission.status = "failed"
        own_candidate = AcquisitionCandidate(
            id="candidate-result-own",
            tenant_id="t1",
            mission_id=own_mission.id,
            status="needs_evidence",
            dedupe_key="domain:result-own.example",
        )
        other_candidate = AcquisitionCandidate(
            id="candidate-result-other",
            tenant_id="t2",
            mission_id=other_mission.id,
            status="eligible",
            dedupe_key="domain:result-other.example",
        )
        session.add_all([own_candidate, other_candidate])
        session.flush()
        session.add_all(
            [
                CandidateEvidence(
                    tenant_id="t1",
                    candidate_id=own_candidate.id,
                    source_url="https://own.example/about",
                    canonical_url="https://own.example/about",
                    content_hash="a" * 64,
                ),
                CandidateEvidence(
                    tenant_id="t2",
                    candidate_id=other_candidate.id,
                    source_url="https://other.example/about",
                    canonical_url="https://other.example/about",
                    content_hash="b" * 64,
                ),
                Job(
                    tenant_id="t1",
                    job_type="website_verify",
                    status="failed",
                    error_code="source_unreachable",
                    payload_json=json.dumps({"candidate_id": own_candidate.id}),
                ),
                Job(
                    tenant_id="t2",
                    job_type="candidate_assess",
                    status="failed",
                    error_code="provider_unavailable",
                    payload_json=json.dumps({"candidate_id": other_candidate.id}),
                ),
            ]
        )
        session.commit()

        result = resolve_mission_result(session, own_mission, tenant_id="t1")
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
        with pytest.raises(ValueError, match="tenant_id mismatch"):
            resolve_mission_result(session, own_mission, tenant_id="t2")


def test_mission_job_projection_normalizes_country_and_ignores_unrelated_rows(
    acquisition_app, seed_acquisition_mission
) -> None:
    import json
    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.mission_results import resolve_mission_result
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="job-projection")
    now = datetime.now(UTC)
    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, mission_id)
        assert mission is not None
        mission.status = "completed"
        jobs = (
            Job(
                id="projection-failed",
                tenant_id="t1",
                job_type="web_discovery",
                status="failed",
                error_code="timeout",
                error_summary="must not leak",
                payload_json=json.dumps({"mission_id": mission.id, "country_code": " mx "}),
                finished_at=now - timedelta(minutes=2),
            ),
            Job(
                id="projection-success",
                tenant_id="t1",
                job_type="web_discovery",
                status="succeeded",
                payload_json=json.dumps({"mission_id": mission.id, "country_code": "MX"}),
                finished_at=now - timedelta(minutes=1),
            ),
            Job(
                id="projection-other-tenant",
                tenant_id="t2",
                job_type="acquisition_plan",
                status="failed",
                payload_json=json.dumps({"mission_id": mission.id}),
            ),
            Job(
                id="projection-other-mission",
                tenant_id="t1",
                job_type="acquisition_plan",
                status="failed",
                payload_json=json.dumps({"mission_id": "another-mission"}),
            ),
            Job(
                id="projection-malformed",
                tenant_id="t1",
                job_type="website_verify",
                status="failed",
                payload_json="not-json",
            ),
        )

        result = resolve_mission_result(
            session,
            mission,
            tenant_id="t1",
            candidates=(),
            jobs=jobs,
        )

    assert result.code == "no_results"
    assert result.counts.failed_jobs == 0
    assert "must not leak" not in result.summary


def test_mission_result_projects_safe_zero_valid_hit_reason(
    acquisition_app, seed_acquisition_mission
) -> None:
    import json

    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.mission_results import resolve_mission_result
    from app.modules.acquisition.models import AcquisitionMission
    from app.modules.jobs.models import Job

    mission_id = seed_acquisition_mission(tenant_id="t1", suffix="zero-valid-hits")
    with Session(get_engine(acquisition_app)) as session:
        mission = session.get(AcquisitionMission, mission_id)
        assert mission is not None
        mission.status = "completed"
        job = Job(
            id="projection-zero-valid-hits",
            tenant_id="t1",
            job_type="web_discovery",
            status="succeeded",
            payload_json=json.dumps({"mission_id": mission.id, "country_code": "MX"}),
            result_summary_json=json.dumps(
                {
                    "hits_received": 0,
                    "valid_hits": 0,
                    "domain_skipped": 0,
                    "query_count": 1,
                }
            ),
        )

        result = resolve_mission_result(
            session,
            mission,
            tenant_id="t1",
            candidates=(),
            jobs=(job,),
        )

    assert result.reason_codes == ("search_no_valid_hits",)


def test_recent_mission_summaries_keep_active_execution_state(
    acquisition_app, seed_acquisition_mission
) -> None:
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.mission_results import list_mission_result_summaries
    from app.modules.acquisition.models import AcquisitionMission

    active_id = seed_acquisition_mission(tenant_id="t1", suffix="summary-active")
    terminal_id = seed_acquisition_mission(tenant_id="t1", suffix="summary-terminal")
    seed_acquisition_mission(tenant_id="t2", suffix="summary-other")
    with Session(get_engine(acquisition_app)) as session:
        active = session.get(AcquisitionMission, active_id)
        terminal = session.get(AcquisitionMission, terminal_id)
        assert active is not None
        assert terminal is not None
        active.status = "running"
        terminal.status = "completed"
        session.commit()

        summaries = list_mission_result_summaries(session, "t1", limit=50)

    by_id = {item.mission_id: item for item in summaries}
    assert set(by_id) == {active_id, terminal_id}
    assert by_id[active_id].execution_status == "running"
    assert by_id[active_id].result is None
    assert by_id[terminal_id].result is not None
    assert by_id[terminal_id].result.code == "no_results"


def test_recent_mission_summaries_batch_terminal_projection_queries(
    acquisition_app, seed_acquisition_mission
) -> None:
    import json

    from sqlalchemy import event
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.acquisition.mission_results import list_mission_result_summaries
    from app.modules.acquisition.models import AcquisitionCandidate, AcquisitionMission
    from app.modules.jobs.models import Job

    mission_ids = [
        seed_acquisition_mission(tenant_id="t1", suffix=f"summary-batch-{index}")
        for index in range(3)
    ]
    engine = get_engine(acquisition_app)
    with Session(engine) as session:
        for index, mission_id in enumerate(mission_ids):
            mission = session.get(AcquisitionMission, mission_id)
            assert mission is not None
            mission.status = "completed"
            candidate_id = f"candidate-summary-batch-{index}"
            session.add(
                AcquisitionCandidate(
                    id=candidate_id,
                    tenant_id="t1",
                    mission_id=mission_id,
                    status="eligible",
                    dedupe_key=f"domain:summary-batch-{index}.example",
                )
            )
            session.add(
                Job(
                    tenant_id="t1",
                    job_type="candidate_assess",
                    status="succeeded",
                    payload_json=json.dumps({"candidate_id": candidate_id}),
                )
            )
        session.commit()

    select_statements: list[str] = []

    def count_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        with Session(engine) as session:
            summaries = list_mission_result_summaries(session, "t1", limit=50)
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert {item.mission_id for item in summaries} == set(mission_ids)
    assert len(select_statements) <= 4
