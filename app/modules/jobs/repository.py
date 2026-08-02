"""Tenant-scoped job repository."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.jobs.models import Job

WORKBENCH_ACTIVE_JOB_STATUSES = ("queued", "running", "retrying")
WORKBENCH_TERMINAL_JOB_STATUSES = ("failed", "succeeded")
MAX_WORKBENCH_TERMINAL_JOBS = 1000


@dataclass(frozen=True)
class TerminalJobProjection:
    jobs: tuple[Job, ...]
    truncated: bool


def _require_tenant(tenant_id: str) -> str:
    clean = (tenant_id or "").strip()
    if not clean:
        raise ValueError("tenant_id is required")
    return clean


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- tenant-bound public API ----

    def create_for_tenant(self, job: Job, *, tenant_id: str) -> Job:
        tenant_id = _require_tenant(tenant_id)
        if not job.tenant_id:
            job.tenant_id = tenant_id
        elif job.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        self.session.add(job)
        return job

    def get_for_tenant(self, job_id: str, *, tenant_id: str) -> Job | None:
        tenant_id = _require_tenant(tenant_id)
        return self.session.scalar(select(Job).where(Job.id == job_id, Job.tenant_id == tenant_id))

    def list_for_tenant(self, *, tenant_id: str, limit: int = 50, offset: int = 0) -> Sequence[Job]:
        tenant_id = _require_tenant(tenant_id)
        query = (
            select(Job)
            .where(Job.tenant_id == tenant_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(query))

    def count_active_for_workbench(self, *, tenant_id: str) -> int:
        tenant_id = _require_tenant(tenant_id)
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    Job.tenant_id == tenant_id,
                    Job.status.in_(WORKBENCH_ACTIVE_JOB_STATUSES),
                )
            )
            or 0
        )

    def list_active_for_workbench(self, *, tenant_id: str, limit: int = 8) -> Sequence[Job]:
        tenant_id = _require_tenant(tenant_id)
        bounded_limit = max(1, min(int(limit), 100))
        query = (
            select(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.status.in_(WORKBENCH_ACTIVE_JOB_STATUSES),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .limit(bounded_limit)
        )
        return list(self.session.scalars(query))

    def has_active_for_candidate(
        self,
        candidate_id: str,
        *,
        job_type: str,
        tenant_id: str,
    ) -> bool:
        """Return whether one exact candidate already has an active job.

        Payload inspection stays in Python because the supported databases do not
        share one portable JSON query syntax. Malformed payloads are ignored rather
        than making a tenant's retry page fail.
        """

        tenant_id = _require_tenant(tenant_id)
        query = select(Job.payload_json).where(
            Job.tenant_id == tenant_id,
            Job.job_type == job_type,
            Job.status.in_(WORKBENCH_ACTIVE_JOB_STATUSES),
        )
        for payload_json in self.session.scalars(query):
            try:
                payload = json.loads(payload_json)
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict) and payload.get("candidate_id") == candidate_id:
                return True
        return False

    def list_recent_terminal_for_workbench(
        self, *, tenant_id: str, limit: int = MAX_WORKBENCH_TERMINAL_JOBS
    ) -> TerminalJobProjection:
        """Return a bounded terminal history and expose when older rows were omitted."""

        tenant_id = _require_tenant(tenant_id)
        bounded_limit = max(1, min(int(limit), MAX_WORKBENCH_TERMINAL_JOBS))
        outcome_at = func.coalesce(Job.finished_at, Job.updated_at, Job.created_at)
        query = (
            select(Job)
            .where(
                Job.tenant_id == tenant_id,
                Job.status.in_(WORKBENCH_TERMINAL_JOB_STATUSES),
            )
            .order_by(
                outcome_at.desc(),
                Job.updated_at.desc(),
                Job.created_at.desc(),
                Job.id.desc(),
            )
            .limit(bounded_limit + 1)
        )
        rows = list(self.session.scalars(query))
        return TerminalJobProjection(
            jobs=tuple(rows[:bounded_limit]),
            truncated=len(rows) > bounded_limit,
        )

    def update_for_tenant(self, job: Job, *, tenant_id: str, **fields: Any) -> Job:
        tenant_id = _require_tenant(tenant_id)
        if job.tenant_id != tenant_id:
            raise ValueError("tenant_id mismatch")
        for key, value in fields.items():
            if value is not None:
                setattr(job, key, value)
        job.updated_at = datetime.now(UTC)
        return job

    # ---- worker-only API (requires explicit tenant_id) ----

    def get_for_worker(self, job_id: str, tenant_id: str) -> Job | None:
        """Worker-side read — same logic as get_for_tenant but named
        explicitly to distinguish from tenant-bound web routes."""
        return self.get_for_tenant(job_id, tenant_id=tenant_id)

    def update_for_worker(self, job: Job, *, tenant_id: str, **fields: Any) -> Job:
        """Worker-side update — enforces tenant_id check."""
        return self.update_for_tenant(job, tenant_id=tenant_id, **fields)

    def list_stale_running(self, *, heartbeat_timeout_minutes: int = 5) -> Sequence[Job]:
        """Return jobs that are ``running`` with no recent heartbeat."""

        cutoff = datetime.now(UTC) - timedelta(minutes=heartbeat_timeout_minutes)
        query = select(Job).where(
            Job.status.in_(["running"]),
            or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff),
        )
        return list(self.session.scalars(query))

    def list_due_retries(self, *, now: datetime | None = None) -> Sequence[Job]:
        due_at = now or datetime.now(UTC)
        query = select(Job).where(
            Job.status == "retrying",
            Job.next_retry_at.is_not(None),
            Job.next_retry_at <= due_at,
        )
        return list(self.session.scalars(query))

    def claim_queued_for_worker(self, job_id: str) -> Job | None:
        """Atomically move a queued job to running and return the claimed row."""
        now = datetime.now(UTC)
        result = self.session.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(status="running", started_at=now, heartbeat_at=now, updated_at=now)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            return None
        self.session.commit()
        return self.session.get(Job, job_id)

    def recover_stale_running_job(
        self, job: Job, *, heartbeat_timeout_minutes: int = 5
    ) -> Job | None:
        """Atomically claim one stale running job for recovery."""
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=heartbeat_timeout_minutes)
        stale_condition = or_(Job.heartbeat_at.is_(None), Job.heartbeat_at < cutoff)

        if job.attempt >= job.max_attempts:
            values = {
                "status": "failed",
                "error_code": "stale_timeout",
                "error_summary": "Job timed out and max attempts reached",
                "finished_at": now,
                "updated_at": now,
            }
        else:
            next_attempt = job.attempt + 1
            values = {
                "status": "queued",
                "attempt": next_attempt,
                "progress_message": f"Recovery re-queue (attempt {next_attempt})",
                "started_at": None,
                "heartbeat_at": None,
                "queued_at": now,
                "updated_at": now,
            }

        result = self.session.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "running", stale_condition)
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            return None
        self.session.commit()
        return self.session.get(Job, job.id)

    def claim_due_retry(self, job: Job, *, now: datetime | None = None) -> Job | None:
        due_at = now or datetime.now(UTC)
        if job.attempt >= job.max_attempts:
            values = {
                "status": "failed",
                "error_code": "max_attempts_reached",
                "error_summary": "Retry limit reached",
                "finished_at": due_at,
                "updated_at": due_at,
            }
        else:
            values = {
                "status": "queued",
                "attempt": job.attempt + 1,
                "queued_at": due_at,
                "started_at": None,
                "heartbeat_at": None,
                "next_retry_at": None,
                "progress_message": f"Retry queued (attempt {job.attempt + 1})",
                "updated_at": due_at,
            }
        result = self.session.execute(
            update(Job)
            .where(
                Job.id == job.id,
                Job.status == "retrying",
                Job.next_retry_at.is_not(None),
                Job.next_retry_at <= due_at,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            self.session.rollback()
            return None
        self.session.commit()
        return self.session.get(Job, job.id)
