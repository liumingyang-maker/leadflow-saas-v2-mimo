from __future__ import annotations

import pytest

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
