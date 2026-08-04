"""Tests for worker bootstrap, contracts, and adapter protocol — V2-04-003."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.integrations.collection.contracts import Candidate


def test_candidate_defaults() -> None:
    c = Candidate()
    assert c.email == ""
    assert c.source == ""


def test_candidate_with_values() -> None:
    c = Candidate(email="a@b.com", company="Acme", domain="acme.com")
    assert c.email == "a@b.com"
    assert c.company == "Acme"
    assert c.domain == "acme.com"


def test_collection_adapter_protocol() -> None:
    """Verify a minimal adapter can be created and follows the protocol."""

    class FakeAdapter:
        def collect(self, *, payload: dict, max_results: int):
            return [Candidate(email="test@test.com")]

    adapter = FakeAdapter()
    # Structural typing: verify the method exists and accepts the right signature
    result = adapter.collect(payload={}, max_results=10)
    assert len(result) == 1


def test_adapter_registry(monkeypatch) -> None:
    from app.modules.jobs.worker import _get_adapter, register_adapter

    class FakeAdapter:
        def collect(self, *, payload, max_results):
            return []

    register_adapter("test_type", FakeAdapter())
    assert _get_adapter("test_type") is not None


def test_execute_job_handles_nonexistent_job(monkeypatch) -> None:
    """Worker should return a safe error for a missing job."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("APP_ENV", "testing")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    Base.metadata.create_all(get_engine(app))

    from app.modules.jobs.worker import execute_job

    result = execute_job("nonexistent-job-id")
    assert isinstance(result, dict)
    assert result["error"] == "job_not_found"


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("APP_ENV", "testing")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    engine = get_engine(app)
    Base.metadata.create_all(engine)
    return app, engine


def test_execute_job_updates_persistently(monkeypatch) -> None:
    from app.integrations.collection.contracts import CollectionResult
    from app.modules.jobs.models import Job
    from app.modules.jobs.worker import execute_job, register_adapter

    app, engine = _app(monkeypatch)

    class EmptyAdapter:
        def collect(self, *, payload, max_results):
            return CollectionResult(found_count=0, candidates=[])

    register_adapter("google_search", EmptyAdapter())
    with Session(engine) as session:
        job = Job(
            tenant_id="t1",
            job_type="google_search",
            payload_json=json.dumps({"query": "acme", "max_results": 1}),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    result = execute_job(job_id)
    assert result == {"ok": True, "created": 0}

    with Session(engine) as session:
        restored = session.get(Job, job_id)
        assert restored is not None
        assert restored.status == "succeeded"
        assert restored.progress == 100


def test_execute_job_refuses_terminal_job(monkeypatch) -> None:
    from app.modules.jobs.models import Job
    from app.modules.jobs.worker import execute_job

    _app_obj, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search", status="succeeded")
        session.add(job)
        session.commit()
        job_id = job.id

    result = execute_job(job_id)
    assert result == {"error": "invalid_status:succeeded", "ok": False}


def test_execute_job_preserves_cancellation_reported_while_a_handler_runs(monkeypatch) -> None:
    import app.modules.jobs.worker as worker
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="radar_scan", payload_json='{"run_id":"run-a"}')
        session.add(job)
        session.commit()
        job_id = job.id

    def cancelled_handler(_app, _job, _payload):
        with Session(engine) as session:
            current = session.get(Job, job_id)
            assert current is not None
            current.status = "cancelled"
            session.commit()
        return {"run_status": "cancelled"}

    monkeypatch.setattr(worker, "_make_app", lambda: app)
    monkeypatch.setattr(worker, "_get_job_handler", lambda _job_type: cancelled_handler)

    assert worker.execute_job(job_id) == {
        "ok": False,
        "error": "cancelled",
        "run_status": "cancelled",
    }
    with Session(engine) as session:
        current = session.get(Job, job_id)
        assert current is not None and current.status == "cancelled"


def test_execute_scheduled_retry_reschedules_an_early_scheduler_delivery(monkeypatch) -> None:
    import app.modules.jobs.worker as worker
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(
            tenant_id="t1",
            job_type="google_search",
            status="retrying",
            next_retry_at=datetime.now(UTC) + timedelta(seconds=5),
        )
        session.add(job)
        session.commit()
        job_id = job.id

    calls = []
    monkeypatch.setattr(worker, "_make_app", lambda: app)
    monkeypatch.setattr(
        worker,
        "schedule_retry",
        lambda _app, *, job_id, tenant_id: calls.append((job_id, tenant_id)),
    )

    assert worker.execute_scheduled_retry(job_id) == {"ok": True, "status": "retry_rescheduled"}
    assert calls == [(job_id, "t1")]
    with Session(engine) as session:
        current = session.get(Job, job_id)
        assert current is not None and current.status == "retrying"


def test_worker_error_does_not_resurrect_a_cancelled_job(monkeypatch) -> None:
    import app.modules.jobs.worker as worker
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="radar_scan", status="cancelled")
        session.add(job)
        session.commit()
        job_id = job.id

    worker._handle_worker_error(app, job_id, "t1", RuntimeError("interrupted"))

    with Session(engine) as session:
        stored = session.get(Job, job_id)
        assert stored is not None and stored.status == "cancelled"


def test_stale_recovery_is_atomic(monkeypatch) -> None:
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    _app_obj, engine = _app(monkeypatch)
    stale_time = datetime.now(UTC) - timedelta(minutes=10)
    with Session(engine) as session:
        job = Job(
            tenant_id="t1",
            job_type="google_search",
            status="running",
            attempt=1,
            max_attempts=3,
            heartbeat_at=stale_time,
        )
        session.add(job)
        session.commit()
        job_id = job.id

    with Session(engine) as s1:
        original = s1.get(Job, job_id)
        assert original is not None
        assert JobRepository(s1).recover_stale_running_job(original) is not None

    with Session(engine) as s2:
        stale_copy = Job(
            id=job_id,
            tenant_id="t1",
            job_type="google_search",
            status="running",
            attempt=1,
            max_attempts=3,
            heartbeat_at=stale_time,
        )
        assert JobRepository(s2).recover_stale_running_job(stale_copy) is None

    with Session(engine) as session:
        restored = session.get(Job, job_id)
        assert restored is not None
        assert restored.status == "queued"
        assert restored.attempt == 2
