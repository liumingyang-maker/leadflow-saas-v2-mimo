"""RQ Worker entry point and job handler registry.

Worker execution flow:
1. RQ calls ``execute_job(job_id)``
2. Read ``Job`` from SQL DB
3. Validate status (must be ``queued``)
4. Mark ``running``
5. Look up adapter by ``job_type``
6. Fetch API keys from ``SecretStore``
7. Execute adapter
8. Save results as pending-review Leads
9. Mark ``succeeded`` or ``failed``/``retrying``
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.jobs.models import Job
from app.modules.jobs.repository import JobRepository
from app.modules.jobs.service import JOB_HANDLER
from app.modules.leads.models import Activity

# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------

_adapters: dict[str, Any] = {}


def register_adapter(job_type: str, adapter: Any) -> None:
    _adapters[job_type] = adapter


def _get_adapter(job_type: str) -> Any:
    adapter = _adapters.get(job_type)
    if adapter is None:
        raise ValueError(f"No adapter registered for job_type={job_type!r}")
    return adapter


def _is_allowed_env() -> bool:
    """Fake adapters are only allowed in development and testing."""
    env = os.environ.get("APP_ENV", "development").lower()
    return env in ("development", "dev", "testing", "test")


# Register adapters based on environment and available API keys
def _register_adapters() -> None:
    from app.integrations.collection.adapters import (  # noqa: E402
        CsvXlsxAdapter,
        GoogleMapsAdapter,
        GoogleSearchAdapter,
    )

    search_api_key = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
    search_cx = os.environ.get("GOOGLE_SEARCH_CX", "")
    maps_api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    if search_api_key and search_cx:
        register_adapter("google_search", GoogleSearchAdapter(api_key=search_api_key, cx=search_cx))
    elif _is_allowed_env():
        from app.integrations.collection.adapters import FakeSearchAdapter  # noqa: E402

        register_adapter("google_search", FakeSearchAdapter())
    else:
        register_adapter("google_search", _NotConfiguredAdapter())

    if maps_api_key:
        register_adapter("google_maps", GoogleMapsAdapter(api_key=maps_api_key))
    elif _is_allowed_env():
        from app.integrations.collection.adapters import FakeMapsAdapter  # noqa: E402

        register_adapter("google_maps", FakeMapsAdapter())
    else:
        register_adapter("google_maps", _NotConfiguredAdapter())

    register_adapter("csv_import", CsvXlsxAdapter())
    register_adapter("xlsx_import", CsvXlsxAdapter())


class _NotConfiguredAdapter:
    """Returns ``integration_not_configured`` for missing providers."""

    def collect(self, *, payload: dict, max_results: int) -> Any:
        from app.integrations.collection.contracts import CollectionResult

        return CollectionResult(
            found_count=0,
            error_code="integration_not_configured",
            error_summary="This collection source is not configured",
            is_transient=False,
        )


_register_adapters()


# ---------------------------------------------------------------------------
# Main entry point (called by RQ)
# ---------------------------------------------------------------------------


def execute_job(job_id: str) -> dict[str, Any]:
    """RQ job entry point.

    Reads everything from the SQL DB — the queue only carries ``job_id``.
    """

    app = _make_app()

    with Session(get_engine(app)) as session:
        repo = JobRepository(session)
        job = repo.claim_queued_for_worker(job_id)
        if job is None:
            current = session.get(Job, job_id)
            if current is None:
                return {"error": "job_not_found", "ok": False}
            return {"error": f"invalid_status:{current.status}", "ok": False}
        tenant_id = job.tenant_id
        job_type = job.job_type
        payload_json = job.payload_json

    try:
        adapter = _get_adapter(job_type)
        payload = json.loads(payload_json or "{}")
        max_results = payload.get("max_results", 100)
        query = payload.get("query", "")

        result = adapter.collect(payload=payload, max_results=max_results)

        if result.error_code:
            _handle_adapter_error(app, job_id, tenant_id, result)
            return {"ok": False, "error": result.error_code}

        # Save candidates as Leads
        created = _save_candidates(app, job_id, tenant_id, job_type, result.candidates)

        # Mark succeeded
        summary = {
            "found": result.found_count,
            "created": created,
            "query": query[:100],
        }
        with Session(get_engine(app)) as session:
            job = _get_job_for_update(session, job_id, tenant_id)
            if job is None:
                return {"ok": False, "error": "job_not_found"}
            _update_job(
                session,
                job,
                status="succeeded",
                progress=100,
                progress_message="Collection completed",
                result_summary_json=json.dumps(summary),
                finished_at=datetime.now(UTC),
            )

        return {"ok": True, "created": created}

    except Exception as exc:
        _handle_worker_error(app, job_id, tenant_id, exc)
        return {"ok": False, "error": "worker_error"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _update_job(session: Session, job: Job, **fields: Any) -> None:
    now = datetime.now(UTC)
    fields.setdefault("updated_at", now)
    for key, value in fields.items():
        setattr(job, key, value)
    session.commit()


def _get_job_for_update(session: Session, job_id: str, tenant_id: str) -> Job | None:
    repo = JobRepository(session)
    return repo.get_for_worker(job_id, tenant_id)


def _make_app() -> Any:
    """Create a minimal Flask app with DB configuration."""
    from app import create_app

    os.environ.setdefault("APP_ENV", "development")
    return create_app(os.environ.get("APP_ENV", "development"))


def _save_candidates(app: Any, job_id: str, tenant_id: str, job_type: str, candidates: list) -> int:
    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    created = 0

    with Session(get_engine(app)) as session:
        repo = LeadRepository(session)
        job = _get_job_for_update(session, job_id, tenant_id)
        if job is None:
            return 0

        for c in candidates:
            email = (c.email or "").strip().lower()
            if not email or "@" not in email:
                continue
            with session.no_autoflush:
                existing = list(repo.list(tenant_id=tenant_id, search=email, limit=1))
            if existing:
                continue

            lead = Lead(
                tenant_id=tenant_id,
                email=email,
                first_name=(c.first_name or "")[:120],
                last_name=(c.last_name or "")[:120],
                company_id=None,
                title=(c.title or "")[:300],
                phone=(c.phone or "")[:60],
                website=(c.website or "")[:500],
                industry=(c.industry or "")[:120],
                source="collection",
                status="pending_review",
                import_batch_id=job_id,
            )
            repo.add(lead, tenant_id=tenant_id)
            session.flush()
            session.add(
                Activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    action="imported",
                    description=f"Collected via {job_type}",
                )
            )
            session.flush()
            created += 1

            # Batch progress update
            if created % 10 == 0:
                job.progress = min(90, int(created / max(len(candidates), 1) * 90))
                session.commit()

        session.commit()
    return created


def _handle_adapter_error(app: Any, job_id: str, tenant_id: str, result: Any) -> None:
    now = datetime.now(UTC)

    with Session(get_engine(app)) as session:
        job = _get_job_for_update(session, job_id, tenant_id)
        if job is None:
            return
        if result.is_transient and job.attempt < job.max_attempts:
            status = "retrying"
            next_retry = now + timedelta(seconds=min(30 * (2**job.attempt), 600))
        else:
            status = "failed"
            next_retry = None
        _update_job(
            session,
            job,
            status=status,
            error_code=result.error_code,
            error_summary=result.error_summary[:500],
            heartbeat_at=now,
            next_retry_at=next_retry,
            finished_at=now if status == "failed" else None,
        )


def _handle_worker_error(app: Any, job_id: str, tenant_id: str, exc: Exception) -> None:
    now = datetime.now(UTC)
    safe_summary = str(type(exc).__name__)[:500]

    with Session(get_engine(app)) as session:
        job = _get_job_for_update(session, job_id, tenant_id)
        if job is None:
            return
        if job.attempt < job.max_attempts:
            status = "retrying"
            next_retry = now + timedelta(seconds=min(30 * (2**job.attempt), 600))
        else:
            status = "failed"
            next_retry = None
        _update_job(
            session,
            job,
            status=status,
            error_code="worker_error",
            error_summary=safe_summary,
            heartbeat_at=now,
            next_retry_at=next_retry,
            finished_at=now if status == "failed" else None,
        )

    # Log the full traceback server-side (secrets still sanitized)
    import logging

    logging.getLogger("worker").error(
        "Job %s failed (attempt %d/%d): %s",
        job_id,
        getattr(job, "attempt", 0),
        getattr(job, "max_attempts", 0),
        safe_summary,
    )


# ---------------------------------------------------------------------------
# Stale job recovery — called on worker startup
# ---------------------------------------------------------------------------


HEARTBEAT_TIMEOUT_MINUTES = 5


def recover_stale_jobs(app: Any) -> int:
    """Find running jobs with no recent heartbeat and recover them.

    If the job still has attempts remaining it is re-queued.
    Otherwise it is marked ``failed``.

    Returns the number of jobs recovered.
    """
    from redis import Redis
    from rq import Queue
    from rq.serializers import JSONSerializer

    recovered = 0
    with Session(get_engine(app)) as session:
        repo = JobRepository(session)
        stale = repo.list_stale_running(heartbeat_timeout_minutes=HEARTBEAT_TIMEOUT_MINUTES)

        for job in stale:
            recovered_job = repo.recover_stale_running_job(
                job, heartbeat_timeout_minutes=HEARTBEAT_TIMEOUT_MINUTES
            )
            if recovered_job is None:
                continue
            if recovered_job.status == "queued":
                try:
                    redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
                    q = Queue(
                        recovered_job.queue_name or "default",
                        connection=Redis.from_url(redis_url),
                        serializer=JSONSerializer,
                    )
                    rq_job = q.enqueue(
                        JOB_HANDLER,
                        recovered_job.id,
                        job_result_ttl=86400,
                    )
                    recovered_job.rq_job_id = rq_job.id or ""
                    session.commit()
                except Exception:
                    recovered_job.status = "failed"
                    recovered_job.error_code = "recovery_failed"
                    recovered_job.error_summary = "Stale job recovery failed"
                    recovered_job.finished_at = datetime.now(UTC)
                    session.commit()
            recovered += 1

    return recovered
