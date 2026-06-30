"""V2-04-010: Job tenant isolation and restart tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def test_job_uuid_hex(monkeypatch) -> None:
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        j1 = Job(tenant_id="t1", job_type="google_search")
        j2 = Job(tenant_id="t2", job_type="google_maps")
        session.add_all([j1, j2])
        session.commit()
        assert len(j1.id) == 32
        assert len(j2.id) == 32
        assert "t1" not in j1.id
        assert j1.id != j2.id


def test_job_tenant_a_cannot_read_b(monkeypatch) -> None:
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        repo = JobRepository(session)
        repo.create_for_tenant(Job(job_type="google_search"), tenant_id="t1")
        session.commit()
        j1_id = repo.list_for_tenant(tenant_id="t1")[0].id

        assert repo.get_for_tenant(j1_id, tenant_id="t1") is not None
        assert repo.get_for_tenant(j1_id, tenant_id="t2") is None


def test_job_tenant_a_cannot_update_b(monkeypatch) -> None:
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        repo = JobRepository(session)
        job = repo.create_for_tenant(Job(job_type="google_search"), tenant_id="t1")
        session.commit()
        with pytest.raises(ValueError, match="tenant_id mismatch"):
            repo.update_for_tenant(job, tenant_id="t2", status="running")


def test_create_and_enqueue_without_redis(monkeypatch) -> None:
    """When Redis is unavailable, the job should be marked failed."""
    from app.modules.jobs.service import create_and_enqueue

    app, engine = _app(monkeypatch)
    app.config["REDIS_URL"] = "redis://localhost:16379/0"  # wrong port

    from app.modules.jobs.service import JobServiceError

    with pytest.raises(JobServiceError):
        create_and_enqueue(app, tenant_id="t1", job_type="google_search", payload={"query": "test"})


def test_job_status_persistence(monkeypatch) -> None:
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search")
        session.add(job)
        session.commit()
        job_id = job.id
        job.status = "running"
        job.progress = 50
        job.progress_message = "Processing..."
        session.commit()

    with Session(engine) as session:
        restored = session.get(Job, job_id)
        assert restored is not None
        assert restored.status == "running"
        assert restored.progress == 50


def test_status_transitions_blocked_by_check(monkeypatch) -> None:
    import sqlalchemy.exc

    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search", status="invalid!")
        session.add(job)
        with pytest.raises(sqlalchemy.exc.IntegrityError):
            session.commit()


def test_progress_boundaries(monkeypatch) -> None:
    import sqlalchemy.exc

    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        for p in [-1, 101]:
            job = Job(tenant_id="t1", job_type="google_search", progress=p)
            session.add(job)
            with pytest.raises(sqlalchemy.exc.IntegrityError):
                session.commit()
            session.rollback()


def test_payload_does_not_contain_secrets(monkeypatch) -> None:
    from app.modules.jobs.models import Job

    app, engine = _app(monkeypatch)
    with Session(engine) as session:
        job = Job(
            tenant_id="t1",
            job_type="google_search",
            payload_json=json.dumps({"query": "test", "max_results": 10}),
        )
        session.add(job)
        session.commit()
        payload = json.loads(job.payload_json)
        assert "api_key" not in payload
        assert "password" not in payload
        assert "secret" not in payload


def test_csrf_protected_collection_forms(monkeypatch) -> None:
    """Collection write endpoints require CSRF in development mode."""
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

    # POST without CSRF -> 400
    resp = client.post("/collection/search", data={"query": "test"})
    assert resp.status_code == 400

    resp = client.post("/collection/maps", data={"query": "test", "location": "NY"})
    assert resp.status_code == 400
