"""Tests for Job model and repository — V2-04-001."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session


def _engine(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return engine


def test_job_model_defaults(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job

    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search")
        session.add(job)
        session.commit()
        assert job.id is not None
        assert len(job.id) == 32  # hex uuid
        assert job.status == "queued"
        assert job.progress == 0
        assert job.attempt == 1
        assert job.max_attempts == 3


def test_job_id_is_hex_uuid_and_no_tenant_leak(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job

    with Session(engine) as session:
        j1 = Job(tenant_id="t1", job_type="google_search")
        j2 = Job(tenant_id="t2", job_type="google_maps")
        session.add_all([j1, j2])
        session.commit()
        # IDs don't contain tenant_id
        assert "t1" not in j1.id
        assert "t2" not in j2.id
        assert j1.id != j2.id


def test_job_repository_tenant_isolation(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    with Session(engine) as session:
        repo = JobRepository(session)
        repo.create_for_tenant(Job(job_type="google_search"), tenant_id="t1")
        repo.create_for_tenant(Job(job_type="google_maps"), tenant_id="t2")
        session.commit()

        t1_jobs = repo.list_for_tenant(tenant_id="t1")
        t2_jobs = repo.list_for_tenant(tenant_id="t2")
        assert len(t1_jobs) == 1
        assert len(t2_jobs) == 1

        t1_id = t1_jobs[0].id
        assert repo.get_for_tenant(t1_id, tenant_id="t1") is not None
        assert repo.get_for_tenant(t1_id, tenant_id="t2") is None


def test_job_status_constraints(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import VALID_STATUSES, Job

    with Session(engine) as session:
        for s in VALID_STATUSES:
            job = Job(tenant_id="t1", job_type="google_search", status=s)
            session.add(job)
        session.commit()
        assert session.scalars(select(Job)).all() is not None

    with Session(engine) as session:
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            invalid = Job(tenant_id="t1", job_type="google_search", status="invalid")
            session.add(invalid)
            session.commit()


def test_job_progress_range(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job

    with Session(engine) as session:
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.IntegrityError):
            job = Job(tenant_id="t1", job_type="google_search", progress=150)
            session.add(job)
            session.commit()


def test_empty_tenant_id_raises_error(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.repository import JobRepository

    with Session(engine) as session:
        repo = JobRepository(session)
        with pytest.raises(ValueError, match="tenant_id is required"):
            repo.list_for_tenant(tenant_id="")


def test_job_has_rq_job_id_field(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job

    with Session(engine) as session:
        job = Job(tenant_id="t1", job_type="google_search", rq_job_id="rq-123")
        session.add(job)
        session.commit()
        assert job.rq_job_id == "rq-123"
