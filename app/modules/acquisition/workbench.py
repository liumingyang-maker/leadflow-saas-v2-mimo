"""Read models and notification services for the solo operator workbench."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.acquisition.mission_results import (
    MissionResultSummary,
    list_mission_result_summaries,
)
from app.modules.acquisition.models import (
    AcquisitionCandidate,
    Notification,
    ProductKnowledgeSnapshot,
)
from app.modules.acquisition.repository import (
    CandidateRepository,
    MissionRepository,
    NotificationRepository,
)
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository
from app.modules.leads.models import Activity, Lead

ALLOWED_NOTIFICATION_KINDS = {
    "mission_completed",
    "mission_partial",
    "mission_failed",
    "provider_failed",
    "job_stuck",
    "backup_stale",
    "radar_change",
}
# Accepted candidates can still require promotion; rejected and promoted candidates have
# ended that workflow, so their older candidate-scoped failures are no longer actionable.
OBSOLETE_FAILURE_TYPES_BY_CANDIDATE_STATUS = {
    "needs_evidence": frozenset({"website_verify"}),
    "accepted": frozenset({"website_verify", "candidate_assess"}),
    "rejected": frozenset({"website_verify", "candidate_assess", "candidate_promote"}),
    "promoted": frozenset({"website_verify", "candidate_assess", "candidate_promote"}),
}


class WorkbenchError(ValueError):
    pass


@dataclass(frozen=True)
class JobSummary:
    id: str
    job_type: str
    status: str
    progress: int
    progress_message: str
    error_summary: str
    target_url: str


@dataclass(frozen=True)
class NotificationSummary:
    id: str
    kind: str
    title: str
    body: str
    target_url: str
    status: str
    created_at: datetime


@dataclass(frozen=True)
class WorkbenchView:
    candidates_to_review: int
    replies_to_handle: int
    jobs_running: int
    jobs_failed: int
    needs_evidence: int
    follow_ups_due: int
    notifications_unread: int
    current_jobs: tuple[JobSummary, ...]
    failed_jobs: tuple[JobSummary, ...]
    next_action_url: str
    review_url: str
    attention_url: str
    has_product_knowledge: bool
    terminal_history_truncated: bool
    recent_missions: tuple[MissionResultSummary, ...]


def _session(app) -> Session:
    db_session = Session(get_engine(app))
    db_session.expire_on_commit = False
    return db_session


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise WorkbenchError("tenant_id is required")
    return clean


def load_workbench(app, *, tenant_id: str, now: datetime | None = None) -> WorkbenchView:
    tenant_id = _require_tenant(tenant_id)
    due_at = now or datetime.now(UTC)
    with _session(app) as db_session:
        job_repo = JobRepository(db_session)
        candidate_repo = CandidateRepository(db_session)
        mission_repo = MissionRepository(db_session)
        candidates_to_review = _count(
            db_session,
            AcquisitionCandidate,
            AcquisitionCandidate.tenant_id == tenant_id,
            AcquisitionCandidate.status == "eligible",
        )
        needs_evidence = _count(
            db_session,
            AcquisitionCandidate,
            AcquisitionCandidate.tenant_id == tenant_id,
            AcquisitionCandidate.status == "needs_evidence",
        )
        jobs_running = job_repo.count_active_for_workbench(tenant_id=tenant_id)
        notifications_unread = _count(
            db_session,
            Notification,
            Notification.tenant_id == tenant_id,
            Notification.status == "unread",
        )
        replies_to_handle = int(
            db_session.scalar(
                select(func.count(distinct(Activity.lead_id))).where(
                    Activity.tenant_id == tenant_id,
                    Activity.action == "inbound_received",
                )
            )
            or 0
        )
        follow_ups_due = _count(
            db_session,
            Lead,
            Lead.tenant_id == tenant_id,
            Lead.follow_up_at.is_not(None),
            Lead.follow_up_at <= due_at,
            Lead.stage.not_in({"won", "lost"}),
        )

        active_jobs = job_repo.list_active_for_workbench(tenant_id=tenant_id, limit=8)
        current_jobs = tuple(_job_summary(job) for job in active_jobs)
        terminal_projection = job_repo.list_recent_terminal_for_workbench(tenant_id=tenant_id)
        jobs_failed, failed_jobs = _unresolved_failures(
            candidate_repo,
            terminal_jobs=terminal_projection.jobs,
            tenant_id=tenant_id,
        )
        review_candidate_id = db_session.scalar(
            select(AcquisitionCandidate.id)
            .where(
                AcquisitionCandidate.tenant_id == tenant_id,
                AcquisitionCandidate.status == "eligible",
            )
            .order_by(
                AcquisitionCandidate.priority_score.desc(),
                AcquisitionCandidate.created_at.asc(),
            )
            .limit(1)
        )
        evidence_mission_id = mission_repo.oldest_id_with_candidate_status(
            "needs_evidence", tenant_id=tenant_id
        )
        has_product_knowledge = (
            db_session.scalar(
                select(ProductKnowledgeSnapshot.id)
                .where(ProductKnowledgeSnapshot.tenant_id == tenant_id)
                .limit(1)
            )
            is not None
        )
        recent_missions = list_mission_result_summaries(
            db_session,
            tenant_id=tenant_id,
            limit=5,
        )

    acquisition_start_url = (
        "/acquisition/missions/new" if has_product_knowledge else "/acquisition/products"
    )
    review_url = (
        f"/acquisition/candidates/{review_candidate_id}"
        if review_candidate_id
        else acquisition_start_url
    )
    attention_url = (
        "/workbench#unresolved-job-failures"
        if jobs_failed
        else (
            f"/acquisition/missions/{evidence_mission_id}"
            if evidence_mission_id
            else "/workbench#active-jobs"
        )
    )
    evidence_url = f"/acquisition/missions/{evidence_mission_id}" if evidence_mission_id else ""
    if jobs_failed:
        next_action_url = "/workbench#unresolved-job-failures"
    elif evidence_url:
        next_action_url = evidence_url
    elif review_candidate_id:
        next_action_url = review_url
    elif replies_to_handle or follow_ups_due:
        next_action_url = "/leads"
    else:
        next_action_url = acquisition_start_url
    return WorkbenchView(
        candidates_to_review=candidates_to_review,
        replies_to_handle=replies_to_handle,
        jobs_running=jobs_running,
        jobs_failed=jobs_failed,
        needs_evidence=needs_evidence,
        follow_ups_due=follow_ups_due,
        notifications_unread=notifications_unread,
        current_jobs=current_jobs,
        failed_jobs=failed_jobs,
        next_action_url=next_action_url,
        review_url=review_url,
        attention_url=attention_url,
        has_product_knowledge=has_product_knowledge,
        terminal_history_truncated=terminal_projection.truncated,
        recent_missions=recent_missions,
    )


def notify_once(
    app,
    *,
    tenant_id: str,
    kind: str,
    dedupe_key: str,
    title: str,
    target_url: str,
    body: str = "",
) -> Notification:
    tenant_id = _require_tenant(tenant_id)
    clean_kind = (kind or "").strip()
    clean_dedupe = (dedupe_key or "").strip()[:500]
    clean_title = " ".join((title or "").split())[:200]
    clean_body = " ".join((body or "").split())[:1000]
    clean_target = _internal_target(target_url)
    if clean_kind not in ALLOWED_NOTIFICATION_KINDS:
        raise WorkbenchError("notification kind is not allowed")
    if not clean_dedupe or not clean_title:
        raise WorkbenchError("notification key and title are required")

    try:
        with _session(app) as db_session:
            repo = NotificationRepository(db_session)
            existing = repo.find_by_dedupe_key(clean_dedupe, tenant_id=tenant_id)
            if existing is not None:
                return existing
            notification = repo.add(
                Notification(
                    kind=clean_kind,
                    title=clean_title,
                    body=clean_body,
                    target_url=clean_target,
                    dedupe_key=clean_dedupe,
                ),
                tenant_id=tenant_id,
            )
            db_session.commit()
            return notification
    except IntegrityError:
        with _session(app) as db_session:
            existing = NotificationRepository(db_session).find_by_dedupe_key(
                clean_dedupe, tenant_id=tenant_id
            )
            if existing is None:
                raise WorkbenchError("notification could not be saved") from None
            return existing


def list_notifications(app, *, tenant_id: str, limit: int = 100) -> tuple[NotificationSummary, ...]:
    tenant_id = _require_tenant(tenant_id)
    bounded_limit = max(1, min(int(limit), 100))
    with _session(app) as db_session:
        rows = list(
            db_session.scalars(
                select(Notification)
                .where(
                    Notification.tenant_id == tenant_id,
                    Notification.status != "archived",
                )
                .order_by(Notification.created_at.desc())
                .limit(bounded_limit)
            )
        )
    return tuple(
        NotificationSummary(
            id=item.id,
            kind=item.kind,
            title=item.title,
            body=item.body,
            target_url=_safe_stored_target(item.target_url),
            status=item.status,
            created_at=item.created_at,
        )
        for item in rows
    )


def mark_notification_read(app, *, tenant_id: str, notification_id: str) -> Notification | None:
    tenant_id = _require_tenant(tenant_id)
    with _session(app) as db_session:
        notification = NotificationRepository(db_session).mark_read(
            notification_id, tenant_id=tenant_id
        )
        if notification is not None:
            db_session.commit()
        return notification


def mark_all_notifications_read(app, *, tenant_id: str) -> int:
    tenant_id = _require_tenant(tenant_id)
    now = datetime.now(UTC)
    with _session(app) as db_session:
        rows = list(
            db_session.scalars(
                select(Notification).where(
                    Notification.tenant_id == tenant_id,
                    Notification.status == "unread",
                )
            )
        )
        for notification in rows:
            notification.status = "read"
            notification.read_at = now
        db_session.commit()
        return len(rows)


def _count(db_session: Session, model, *conditions) -> int:
    return int(db_session.scalar(select(func.count()).select_from(model).where(*conditions)) or 0)


def _unresolved_failures(
    candidate_repo: CandidateRepository,
    *,
    terminal_jobs: Sequence[Job],
    tenant_id: str,
) -> tuple[int, tuple[JobSummary, ...]]:
    latest_by_identity: dict[tuple[str, ...], Job] = {}
    for job in terminal_jobs:
        identity = _job_identity(job)
        if identity not in latest_by_identity:
            latest_by_identity[identity] = job

    failures = [job for job in latest_by_identity.values() if job.status == "failed"]
    candidate_ids = {
        identity[2]
        for identity, job in latest_by_identity.items()
        if job.status == "failed" and identity[1] == "candidate"
    }
    candidate_statuses = candidate_repo.statuses_by_ids(tuple(candidate_ids), tenant_id=tenant_id)
    unresolved = [
        job
        for job in failures
        if not (
            (identity := _job_identity(job))[1] == "candidate"
            and job.job_type
            in OBSOLETE_FAILURE_TYPES_BY_CANDIDATE_STATUS.get(
                candidate_statuses.get(identity[2], ""), frozenset()
            )
        )
    ]
    return len(unresolved), tuple(_job_summary(job) for job in unresolved[:8])


def _job_summary(job: Job) -> JobSummary:
    return JobSummary(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        progress=job.progress,
        progress_message=job.progress_message,
        error_summary=job.error_summary,
        target_url=_job_target(job),
    )


def _job_identity(job: Job) -> tuple[str, ...]:
    payload = _job_payload(job)
    mission_id = payload.get("mission_id")
    if job.job_type == "web_discovery":
        if isinstance(mission_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mission_id):
            country_code = payload.get("country_code")
            if isinstance(country_code, str):
                normalized_country = country_code.strip().upper()
                if re.fullmatch(r"[A-Z]{2}", normalized_country):
                    return (
                        job.job_type,
                        "mission_country",
                        mission_id,
                        normalized_country,
                    )
        return (job.job_type, "job", job.id)
    candidate_id = payload.get("candidate_id")
    if isinstance(candidate_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate_id):
        return (job.job_type, "candidate", candidate_id)
    if isinstance(mission_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mission_id):
        return (job.job_type, "mission", mission_id)
    return (job.job_type, "job", job.id)


def _job_payload(job: Job) -> dict:
    try:
        payload = json.loads(job.payload_json or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _job_target(job: Job) -> str:
    payload = _job_payload(job)
    mission_id = payload.get("mission_id")
    if isinstance(mission_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", mission_id):
        return f"/acquisition/missions/{mission_id}"
    candidate_id = payload.get("candidate_id")
    if isinstance(candidate_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate_id):
        return f"/acquisition/candidates/{candidate_id}"
    return "/workbench"


def _internal_target(value: str) -> str:
    clean = (value or "").strip()
    parsed = urlsplit(clean)
    if (
        not clean.startswith("/")
        or clean.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in clean
        or any(ord(character) < 32 for character in clean)
        or len(clean) > 500
    ):
        raise WorkbenchError("notification target must be an internal path")
    return clean


def _safe_stored_target(value: str) -> str:
    try:
        return _internal_target(value)
    except WorkbenchError:
        return "/workbench"
