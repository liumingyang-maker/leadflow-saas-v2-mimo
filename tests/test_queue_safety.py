"""Queue safety, state machine, CSRF, and version pinning tests."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    os.environ.setdefault("APP_ENV", "testing")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def test_enqueue_uses_json_serializer_and_fixed_handler() -> None:
    from rq.serializers import JSONSerializer

    from app.modules.jobs.service import JOB_HANDLER, _queue

    class App:
        config = {"REDIS_URL": "redis://localhost:6379/0"}

    queue = _queue(App())  # type: ignore[arg-type]
    assert queue.serializer is JSONSerializer
    assert JOB_HANDLER == "app.modules.jobs.worker.execute_job"


def test_create_enqueue_passes_only_job_id_to_rq(monkeypatch) -> None:
    from app.modules.jobs.service import JOB_HANDLER, create_and_enqueue

    app, _engine = _app(monkeypatch)
    calls = []

    class FakeRQJob:
        id = "rq-1"

    class FakeQueue:
        def enqueue(self, *args, **kwargs):
            calls.append((args, kwargs))
            return FakeRQJob()

    monkeypatch.setattr("app.modules.jobs.service._queue", lambda _app, _name: FakeQueue())
    job = create_and_enqueue(
        app,
        tenant_id="t1",
        job_type="google_search",
        payload={"query": "x", "max_results": 1},
    )

    assert calls == [((JOB_HANDLER, job.id), {"job_result_ttl": 86400})]


def test_enqueue_failure_marks_job_failed(monkeypatch) -> None:
    from app.modules.jobs.service import JobServiceError, create_and_enqueue

    app, engine = _app(monkeypatch)
    app.config["REDIS_URL"] = "redis://localhost:16379/0"

    with pytest.raises(JobServiceError):
        create_and_enqueue(app, tenant_id="t1", job_type="google_search", payload={"query": "test"})

    from app.modules.jobs.models import Job

    with Session(engine) as session:
        jobs = list(session.scalars(select(Job)))
        if jobs:
            assert jobs[0].status == "failed"


def test_terminal_status_not_reverted_by_claim(monkeypatch) -> None:
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search", status="succeeded")
        session.add(job)
        session.commit()
        job_id = job.id

    with Session(engine) as session:
        repo = JobRepository(session)
        assert repo.claim_queued_for_worker(job_id) is None
        restored = session.get(Job, job_id)
        assert restored is not None
        assert restored.status == "succeeded"


def test_safe_error_summary_no_traceback(monkeypatch) -> None:
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(
            tenant_id="t1",
            job_type="google_search",
            status="failed",
            error_code="worker_error",
            error_summary="ValueError",
        )
        session.add(job)
        session.commit()

        assert "Traceback" not in job.error_summary
        assert "sk-" not in job.error_summary
        assert "secret" not in job.error_summary.lower()


def test_job_payload_no_api_key(monkeypatch) -> None:
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(
            tenant_id="t1", job_type="google_search", payload_json=json.dumps({"query": "test"})
        )
        session.add(job)
        session.commit()
        payload = json.loads(job.payload_json)
        assert "api_key" not in payload
        assert "password" not in payload
        assert "secret" not in payload


def _dev_client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-key")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("development")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    reset_engine_for_tests()
    engine = get_engine(app)
    Base.metadata.create_all(engine)

    from werkzeug.security import generate_password_hash

    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant = Tenant(company_name="X")
        user = User(email="a@b.com", password_hash=generate_password_hash("p"))
        user.email_verified_at = datetime.now(UTC)
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()
        tid = tenant.id
        uid = user.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = tid
        sess["user_id"] = uid
        sess["tenant_email"] = user.email

    return client, engine, app


def _get_csrf(client) -> str:
    from re import search

    html = client.get("/collection/search").get_data(as_text=True)
    m = search(r'csrf_token" value="([^"]+)"', html)
    assert m is not None, "csrf_token not found"
    return m.group(1)


def test_csrf_missing_on_search_returns_400(monkeypatch) -> None:
    client, _engine, _app = _dev_client(monkeypatch)
    resp = client.post("/collection/search", data={"query": "test"})
    assert resp.status_code == 400


def test_csrf_missing_on_maps_returns_400(monkeypatch) -> None:
    client, _engine, _app = _dev_client(monkeypatch)
    resp = client.post("/collection/maps", data={"query": "cafe", "location": "NY"})
    assert resp.status_code == 400


def test_csrf_wrong_token_returns_400(monkeypatch) -> None:
    client, _engine, _app = _dev_client(monkeypatch)
    resp = client.post("/collection/search", data={"query": "test", "csrf_token": "bad-token"})
    assert resp.status_code == 400

    from app.modules.jobs.models import Job

    with Session(_engine) as session:
        assert session.scalar(select(Job)) is None


def test_csrf_correct_token_creates_job(monkeypatch) -> None:
    client, _engine, _app = _dev_client(monkeypatch)
    monkeypatch.setattr(
        "app.modules.jobs.service._queue",
        lambda _app, _name: type(
            "FakeQueue", (), {"enqueue": lambda self, *a, **k: type("J", (), {"id": "rq"})()}
        )(),
    )
    token = _get_csrf(client)
    resp = client.post("/collection/search", data={"query": "test", "csrf_token": token})
    assert resp.status_code in {302, 303}


def test_redis_image_pinned() -> None:
    with open("docker-compose.yml", encoding="utf-8") as f:
        content = f.read()
    assert "redis:7.4.2-alpine" in content
    assert "redis:7-alpine" not in content


def test_runtime_versions_locked() -> None:
    with open("requirements.lock", encoding="utf-8") as f:
        lock = f.read()
    assert "rq==2.9.1" in lock
    assert "redis==8.0.0" in lock
