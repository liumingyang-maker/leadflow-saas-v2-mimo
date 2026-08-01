"""Job service — enqueue, status, worker callbacks."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from flask import Flask
from redis import Redis
from rq import Queue
from rq.serializers import JSONSerializer

from app.extensions import get_engine
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository


class JobServiceError(ValueError):
    pass


JOB_HANDLER = "app.modules.jobs.worker.execute_job"
_FORBIDDEN_PAYLOAD_KEYS = {"api_key", "password", "secret", "authorization", "cookie"}


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------


def _redis_from_app(app: Flask) -> Redis:
    url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(url)


def _queue(app: Flask, name: str = "default") -> Queue:
    return Queue(name, connection=_redis_from_app(app), serializer=JSONSerializer)


def _session(app: Flask):
    from sqlalchemy.orm import Session

    return Session(get_engine(app))


# ---------------------------------------------------------------------------
# Create & enqueue
# ---------------------------------------------------------------------------


def create_and_enqueue(
    app: Flask,
    *,
    tenant_id: str,
    job_type: str,
    payload: dict[str, Any] | None = None,
    queue_name: str = "default",
) -> Job:
    """Create a queued Job, commit to DB, then enqueue.

    If enqueue fails the job becomes ``failed`` — it never stays
    permanently ``queued`` without a matching RQ job.
    """
    clean_payload = payload or {}
    if _contains_forbidden_key(clean_payload):
        raise JobServiceError("job payload contains forbidden key")
    try:
        payload_json = json.dumps(clean_payload, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise JobServiceError("job payload must be JSON serializable") from exc

    now = datetime.now(UTC)
    job = Job(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        job_type=job_type,
        status="queued",
        payload_json=payload_json,
        queue_name=queue_name,
        created_at=now,
        queued_at=now,
    )

    with _session(app) as session:
        repo = JobRepository(session)
        repo.create_for_tenant(job, tenant_id=tenant_id)
        session.commit()
        saved_id = job.id

    # Enqueue after commit — DB is the source of truth
    try:
        q = _queue(app, queue_name)
        rq_job = q.enqueue(
            JOB_HANDLER,
            saved_id,
            job_result_ttl=86400,
        )
        # Update the RQ job ID
        with _session(app) as session:
            stored = session.get(Job, saved_id)
            if stored:
                stored.rq_job_id = rq_job.id or ""
                session.commit()
    except Exception:
        # Enqueue failed — mark job as failed
        with _session(app) as session:
            stored = session.get(Job, saved_id)
            if stored:
                stored.status = "failed"
                stored.error_code = "enqueue_failed"
                stored.error_summary = "Failed to queue job"
                stored.finished_at = datetime.now(UTC)
                session.commit()
        raise JobServiceError("Failed to queue job") from None

    return job


def _contains_forbidden_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _FORBIDDEN_PAYLOAD_KEYS or any(
                normalized.endswith(f"_{forbidden}") for forbidden in _FORBIDDEN_PAYLOAD_KEYS
            ):
                return True
            if _contains_forbidden_key(nested):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_contains_forbidden_key(item) for item in value)
    return False


# ---------------------------------------------------------------------------
# Status (read-only for web)
# ---------------------------------------------------------------------------


def get_job_status(app: Flask, *, job_id: str, tenant_id: str) -> Job | None:
    with _session(app) as session:
        repo = JobRepository(session)
        return repo.get_for_tenant(job_id, tenant_id=tenant_id)


def list_jobs(app: Flask, *, tenant_id: str, limit: int = 50) -> list[Job]:
    with _session(app) as session:
        repo = JobRepository(session)
        return list(repo.list_for_tenant(tenant_id=tenant_id, limit=limit))
