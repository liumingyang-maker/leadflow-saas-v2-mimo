"""Tests for Job model and repository — V2-04-001."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

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


def test_active_candidate_job_lookup_matches_exact_tenant_type_status_and_payload(
    monkeypatch,
) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    with Session(engine) as session:
        session.add_all(
            [
                Job(
                    tenant_id="t1",
                    job_type="website_verify",
                    status="running",
                    payload_json=json.dumps({"candidate_id": "candidate-1"}),
                ),
                Job(
                    tenant_id="t1",
                    job_type="website_verify",
                    status="failed",
                    payload_json=json.dumps({"candidate_id": "historical"}),
                ),
                Job(
                    tenant_id="t2",
                    job_type="website_verify",
                    status="queued",
                    payload_json=json.dumps({"candidate_id": "private"}),
                ),
                Job(
                    tenant_id="t1",
                    job_type="candidate_assess",
                    status="queued",
                    payload_json=json.dumps({"candidate_id": "different-type"}),
                ),
                Job(
                    tenant_id="t1",
                    job_type="website_verify",
                    status="retrying",
                    payload_json="not-json",
                ),
            ]
        )
        session.commit()
        repo = JobRepository(session)

        assert repo.has_active_for_candidate(
            "candidate-1", job_type="website_verify", tenant_id="t1"
        )
        assert not repo.has_active_for_candidate(
            "historical", job_type="website_verify", tenant_id="t1"
        )
        assert not repo.has_active_for_candidate(
            "private", job_type="website_verify", tenant_id="t1"
        )
        assert not repo.has_active_for_candidate(
            "different-type", job_type="website_verify", tenant_id="t1"
        )


def test_job_repository_atomically_cancels_only_tenant_owned_queued_job(monkeypatch) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import JobRepository

    with Session(engine) as session:
        queued = Job(tenant_id="t1", job_type="website_verify", status="queued")
        running = Job(tenant_id="t1", job_type="website_verify", status="running")
        private = Job(tenant_id="t2", job_type="website_verify", status="queued")
        session.add_all([queued, running, private])
        session.commit()
        queued_id = queued.id
        running_id = running.id
        private_id = private.id
        repo = JobRepository(session)

        assert repo.cancel_queued_for_tenant(queued_id, tenant_id="t1") is True
        assert repo.cancel_queued_for_tenant(running_id, tenant_id="t1") is False
        assert repo.cancel_queued_for_tenant(private_id, tenant_id="t1") is False
        session.commit()

    with Session(engine) as session:
        assert session.get(Job, queued_id).status == "cancelled"
        assert session.get(Job, running_id).status == "running"
        assert session.get(Job, private_id).status == "queued"


def test_workbench_terminal_projection_has_hard_bound_and_reports_truncation(
    monkeypatch,
) -> None:
    engine = _engine(monkeypatch)
    from app.modules.jobs.models import Job
    from app.modules.jobs.repository import (
        MAX_WORKBENCH_TERMINAL_JOBS,
        JobRepository,
    )

    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add_all(
            [
                Job(
                    tenant_id="t1",
                    job_type="acquisition_plan",
                    status="failed",
                    finished_at=now - timedelta(seconds=index),
                )
                for index in range(MAX_WORKBENCH_TERMINAL_JOBS + 1)
            ]
        )
        session.add(
            Job(
                tenant_id="t2",
                job_type="acquisition_plan",
                status="failed",
                finished_at=now + timedelta(days=1),
            )
        )
        session.commit()

        projection = JobRepository(session).list_recent_terminal_for_workbench(tenant_id="t1")

    assert len(projection.jobs) == MAX_WORKBENCH_TERMINAL_JOBS
    assert projection.truncated is True
    assert {job.tenant_id for job in projection.jobs} == {"t1"}
    assert projection.jobs[0].finished_at == now.replace(tzinfo=None)


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
