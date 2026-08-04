"""Tenant-scoped projection of acquisition Missions into business results."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.modules.acquisition.models import AcquisitionCandidate, AcquisitionMission
from app.modules.acquisition.repository import (
    CandidateRepository,
    EvidenceRepository,
    MissionRepository,
)
from app.modules.acquisition.states import (
    BusinessResult,
    BusinessResultFacts,
    BusinessResultResolver,
    CandidateResultFact,
    JobResultFact,
)
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository

ACQUISITION_RESULT_JOB_TYPES = (
    "acquisition_plan",
    "web_discovery",
    "website_verify",
    "candidate_assess",
)
_ACTIVE_MISSION_STATUSES = frozenset({"draft", "queued", "running", "paused"})
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


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
    return _resolve_business_result(
        mission,
        candidate_rows,
        evidence_counts,
        _mission_job_facts(
            mission.id,
            candidate_ids,
            job_rows,
            tenant_id=tenant_id,
        ),
    )


def list_mission_result_summaries(
    session: Session, tenant_id: str, limit: int = 50
) -> tuple[MissionResultSummary, ...]:
    missions = MissionRepository(session).list_recent(tenant_id=tenant_id, limit=limit)
    terminal_missions = [
        mission for mission in missions if mission.status not in _ACTIVE_MISSION_STATUSES
    ]
    terminal_ids = tuple(mission.id for mission in terminal_missions)
    candidate_rows = tuple(
        CandidateRepository(session).list_for_missions(terminal_ids, tenant_id=tenant_id)
    )
    candidates_by_mission: dict[str, list[AcquisitionCandidate]] = defaultdict(list)
    for candidate in candidate_rows:
        candidates_by_mission[candidate.mission_id].append(candidate)
    evidence_counts = EvidenceRepository(session).counts_by_candidate_ids(
        tuple(candidate.id for candidate in candidate_rows), tenant_id=tenant_id
    )
    job_rows = tuple(
        JobRepository(session).list_by_types_for_tenant(
            ACQUISITION_RESULT_JOB_TYPES, tenant_id=tenant_id
        )
        if terminal_missions
        else ()
    )
    jobs_by_mission = _mission_job_facts_by_mission(
        terminal_ids,
        candidate_rows,
        job_rows,
        tenant_id=tenant_id,
    )
    return tuple(
        MissionResultSummary(
            mission_id=mission.id,
            name=mission.name,
            execution_status=mission.status,
            result=(
                None
                if mission.status in _ACTIVE_MISSION_STATUSES
                else _resolve_business_result(
                    mission,
                    tuple(candidates_by_mission.get(mission.id, ())),
                    evidence_counts,
                    jobs_by_mission.get(mission.id, ()),
                )
            ),
            target_url=f"/acquisition/missions/{mission.id}",
            created_at=mission.created_at,
        )
        for mission in missions
    )


def _resolve_business_result(
    mission: AcquisitionMission,
    candidates: Sequence[AcquisitionCandidate],
    evidence_counts: Mapping[str, int],
    jobs: Sequence[JobResultFact],
) -> BusinessResult:
    facts = BusinessResultFacts(
        execution_status=mission.status,
        candidates=tuple(
            CandidateResultFact(row.id, row.status, evidence_counts.get(row.id, 0))
            for row in candidates
        ),
        jobs=tuple(jobs),
    )
    return BusinessResultResolver.resolve(facts)


def _mission_job_facts(
    mission_id: str,
    candidate_ids: Sequence[str],
    jobs: Sequence[Job],
    *,
    tenant_id: str,
) -> tuple[JobResultFact, ...]:
    candidate_scope = set(candidate_ids)
    relevant: list[tuple[Job, str]] = []
    for job in jobs:
        if job.tenant_id != tenant_id or job.job_type not in ACQUISITION_RESULT_JOB_TYPES:
            continue
        payload = _payload_object(job.payload_json)
        identity = _mission_job_identity(
            job,
            payload,
            mission_id=mission_id,
            candidate_ids=candidate_scope,
        )
        if identity is not None:
            relevant.append((job, identity))

    return _ordered_job_facts(relevant)


def _mission_job_facts_by_mission(
    mission_ids: Sequence[str],
    candidates: Sequence[AcquisitionCandidate],
    jobs: Sequence[Job],
    *,
    tenant_id: str,
) -> dict[str, tuple[JobResultFact, ...]]:
    mission_scope = set(mission_ids)
    if not mission_scope:
        return {}
    candidate_missions = {
        candidate.id: candidate.mission_id
        for candidate in candidates
        if candidate.tenant_id == tenant_id and candidate.mission_id in mission_scope
    }
    candidate_ids_by_mission: dict[str, set[str]] = defaultdict(set)
    for candidate_id, mission_id in candidate_missions.items():
        candidate_ids_by_mission[mission_id].add(candidate_id)

    relevant_by_mission: dict[str, list[tuple[Job, str]]] = defaultdict(list)
    for job in jobs:
        if job.tenant_id != tenant_id or job.job_type not in ACQUISITION_RESULT_JOB_TYPES:
            continue
        payload = _payload_object(job.payload_json)
        if job.job_type in {"acquisition_plan", "web_discovery"}:
            mission_id = payload.get("mission_id")
            if not isinstance(mission_id, str) or mission_id not in mission_scope:
                continue
        else:
            candidate_id = payload.get("candidate_id")
            if not isinstance(candidate_id, str) or not _SAFE_ID.fullmatch(candidate_id):
                continue
            mission_id = candidate_missions.get(candidate_id)
            if mission_id is None:
                continue
        identity = _mission_job_identity(
            job,
            payload,
            mission_id=mission_id,
            candidate_ids=candidate_ids_by_mission.get(mission_id, set()),
        )
        if identity is not None:
            relevant_by_mission[mission_id].append((job, identity))

    return {
        mission_id: _ordered_job_facts(relevant)
        for mission_id, relevant in relevant_by_mission.items()
    }


def _ordered_job_facts(relevant: Sequence[tuple[Job, str]]) -> tuple[JobResultFact, ...]:
    ordered = sorted(relevant, key=lambda pair: job_outcome_key(pair[0]))
    return tuple(
        JobResultFact(
            identity=identity,
            job_type=job.job_type,
            status=job.status,
            error_code=job.error_code,
            outcome_order=order,
            search_no_valid_hits=_is_safe_zero_valid_hit_discovery(job),
        )
        for order, (job, identity) in enumerate(ordered, start=1)
    )


def _is_safe_zero_valid_hit_discovery(job: Job) -> bool:
    if job.job_type != "web_discovery" or job.status != "succeeded":
        return False
    summary = _payload_object(job.result_summary_json)
    valid_hits = summary.get("valid_hits")
    return isinstance(valid_hits, int) and not isinstance(valid_hits, bool) and valid_hits == 0


def _mission_job_identity(
    job: Job,
    payload: dict[str, object],
    *,
    mission_id: str,
    candidate_ids: set[str],
) -> str | None:
    if job.job_type in {"acquisition_plan", "web_discovery"}:
        payload_mission_id = payload.get("mission_id")
        if payload_mission_id != mission_id:
            return None
        if job.job_type == "acquisition_plan":
            return f"acquisition_plan:mission:{mission_id}"
        country = payload.get("country_code")
        if isinstance(country, str):
            normalized_country = country.strip().upper()
            if re.fullmatch(r"[A-Z]{2}", normalized_country):
                return f"web_discovery:mission:{mission_id}:country:{normalized_country}"
        return f"web_discovery:mission:{mission_id}:job:{job.id}"

    candidate_id = payload.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or not _SAFE_ID.fullmatch(candidate_id)
        or candidate_id not in candidate_ids
    ):
        return None
    return f"{job.job_type}:candidate:{candidate_id}"


def _payload_object(payload_json: str) -> dict[str, object]:
    try:
        payload = json.loads(payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def job_outcome_key(job: Job) -> tuple[float, float, float, str]:
    return (
        _timestamp(job.finished_at or job.updated_at or job.created_at),
        _timestamp(job.updated_at),
        _timestamp(job.created_at),
        job.id,
    )


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()
