"""Tenant-scoped job repository."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.modules.jobs.models import Job


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
