"""Tenant-scoped projection of acquisition Missions into business results."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
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
    facts = BusinessResultFacts(
        execution_status=mission.status,
        candidates=tuple(
            CandidateResultFact(row.id, row.status, evidence_counts.get(row.id, 0))
            for row in candidate_rows
        ),
        jobs=_mission_job_facts(
            mission.id,
            candidate_ids,
            job_rows,
            tenant_id=tenant_id,
        ),
    )
    return BusinessResultResolver.resolve(facts)


def list_mission_result_summaries(
    session: Session, tenant_id: str, limit: int = 50
) -> tuple[MissionResultSummary, ...]:
    missions = MissionRepository(session).list_recent(tenant_id=tenant_id, limit=limit)
    return tuple(
        MissionResultSummary(
            mission_id=mission.id,
            name=mission.name,
            execution_status=mission.status,
            result=(
                None
                if mission.status in _ACTIVE_MISSION_STATUSES
                else resolve_mission_result(session, mission, tenant_id=tenant_id)
            ),
            target_url=f"/acquisition/missions/{mission.id}",
            created_at=mission.created_at,
        )
        for mission in missions
    )


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

    relevant.sort(key=lambda pair: _outcome_key(pair[0]))
    return tuple(
        JobResultFact(
            identity=identity,
            job_type=job.job_type,
            status=job.status,
            error_code=job.error_code,
            outcome_order=order,
        )
        for order, (job, identity) in enumerate(relevant, start=1)
    )


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


def _outcome_key(job: Job) -> tuple[float, float, float, str]:
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
