"""State invariants shared by acquisition services and workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.modules.acquisition.models import AcquisitionCandidate

HUMAN_TERMINAL_STATUSES = frozenset({"accepted", "promoted", "rejected"})
USABLE_CANDIDATE_STATUSES = frozenset({"eligible", "accepted", "promoted"})
_HUMAN_DECISION_FIELDS = (
    "status",
    "eligibility_code",
    "decision_reason_code",
    "decided_by",
    "decided_at",
)

BusinessResultCode = Literal[
    "ready", "needs_review", "partial", "no_results", "failed", "cancelled"
]
TERMINAL_JOB_OUTCOME_STATUSES = frozenset({"succeeded", "failed", "cancelled"})


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
    search_no_valid_hits: bool = False


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


_RESULT_PRESENTATION: dict[BusinessResultCode, tuple[str, str, str, str]] = {
    "ready": ("可审核", "success", "review_candidates", "审核候选"),
    "needs_review": ("待补证", "attention", "complete_evidence", "补充候选证据"),
    "partial": ("部分完成", "warning", "review_partial_results", "查看部分结果"),
    "no_results": ("未找到结果", "neutral", "refine_search", "调整条件后重试"),
    "failed": ("执行失败", "danger", "retry_mission", "检查原因并重试"),
    "cancelled": ("已取消", "neutral", "none", "无需操作"),
}

_FAILURE_REASONS = {
    "acquisition_plan": "planning_failed",
    "web_discovery": "search_failed",
    "website_verify": "verification_failed",
    "candidate_assess": "ai_analysis_failed",
}


class BusinessResultResolver:
    @classmethod
    def resolve(cls, facts: BusinessResultFacts) -> BusinessResult:
        latest_jobs: dict[str, JobResultFact] = {}
        for job in facts.jobs:
            if job.status not in TERMINAL_JOB_OUTCOME_STATUSES:
                continue
            current = latest_jobs.get(job.identity)
            if current is None or job.outcome_order > current.outcome_order:
                latest_jobs[job.identity] = job

        failed_jobs = tuple(job for job in latest_jobs.values() if job.status == "failed")
        counts = BusinessResultCounts(
            discovered=len(facts.candidates),
            needs_review=sum(
                item.status in {"discovered", "verifying", "needs_evidence"}
                for item in facts.candidates
            ),
            ready_to_review=sum(item.status == "eligible" for item in facts.candidates),
            crm_ready=sum(item.status in {"accepted", "promoted"} for item in facts.candidates),
            excluded=sum(item.status == "rejected" for item in facts.candidates),
            evidence=sum(max(0, item.evidence_count) for item in facts.candidates),
            failed_jobs=len(failed_jobs),
            verification_failed=sum(job.job_type == "website_verify" for job in failed_jobs),
            ai_analysis_failed=sum(job.job_type == "candidate_assess" for job in failed_jobs),
        )

        has_material = counts.discovered > 0 or counts.evidence > 0
        if facts.execution_status == "cancelled":
            code: BusinessResultCode = "cancelled"
        elif (failed_jobs or facts.execution_status == "failed") and has_material:
            code = "partial"
        elif failed_jobs or facts.execution_status == "failed":
            code = "failed"
        elif counts.ready_to_review or counts.crm_ready:
            code = "ready"
        elif counts.needs_review:
            code = "needs_review"
        else:
            code = "no_results"

        reason_codes = {
            _FAILURE_REASONS.get(job.job_type, "execution_failed") for job in failed_jobs
        }
        if facts.execution_status == "failed" and has_material and not failed_jobs:
            reason_codes.add("legacy_failed_with_results")
        if code == "no_results":
            if counts.excluded:
                reason_codes.add("all_candidates_excluded")
            elif any(job.search_no_valid_hits for job in latest_jobs.values()):
                reason_codes.add("search_no_valid_hits")
            else:
                reason_codes.add("completed_without_candidates")

        label, tone, action_code, action_label = _RESULT_PRESENTATION[code]
        summary_parts = [
            f"已发现 {counts.discovered}",
            f"待补证 {counts.needs_review}",
            f"可审核 {counts.ready_to_review}",
            f"可进入 CRM {counts.crm_ready}",
            f"已排除 {counts.excluded}",
        ]
        if counts.verification_failed:
            summary_parts.append(f"验证失败 {counts.verification_failed}")
        if counts.ai_analysis_failed:
            summary_parts.append(f"AI 分析失败 {counts.ai_analysis_failed}")

        return BusinessResult(
            code=code,
            label=label,
            tone=tone,
            action_code=action_code,
            action_label=action_label,
            summary="；".join(summary_parts),
            reason_codes=tuple(sorted(reason_codes)),
            counts=counts,
        )


def update_assessment_state_if_mutable(
    session: Session,
    candidate: AcquisitionCandidate,
    *,
    tenant_id: str,
    status: str,
    eligibility_code: str,
) -> str:
    """Atomically apply an automated decision unless a human decision already won."""
    session.flush()
    result = session.execute(
        update(AcquisitionCandidate)
        .where(
            AcquisitionCandidate.id == candidate.id,
            AcquisitionCandidate.tenant_id == tenant_id,
            AcquisitionCandidate.status.not_in(HUMAN_TERMINAL_STATUSES),
        )
        .values(status=status, eligibility_code=eligibility_code),
        execution_options={"synchronize_session": False},
    )
    if result.rowcount not in {0, 1}:
        raise RuntimeError("candidate assessment state update affected unexpected rows")
    session.refresh(candidate, attribute_names=list(_HUMAN_DECISION_FIELDS))
    return candidate.status
