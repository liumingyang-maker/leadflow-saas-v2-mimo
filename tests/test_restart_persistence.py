"""File-based SQLite persistence tests — prove cross-restart durability.

Uses temporary file databases. Multiple app/engine instances access
the same file to simulate worker and web process restarts.
"""

from __future__ import annotations

import json
import os
import tempfile

from sqlalchemy.orm import Session


def _create_app(db_path: str, env_name: str = "testing"):
    """Create a fresh Flask app + engine pointed at *db_path*."""
    import os as _os

    _os.environ["SECRET_KEY"] = "test-secret-key-that-is-long-enough"
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app(env_name)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    reset_engine_for_tests()
    engine = get_engine(app)
    Base.metadata.create_all(engine)
    return app, engine


def _dispose(engine) -> None:
    """Dispose engine and clear module caches."""
    engine.dispose()
    from app.extensions import reset_engine_for_tests

    reset_engine_for_tests()


def test_job_survives_app_restart() -> None:
    """Create a Job with App A, dispose, read it with App B."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "restart-test.db")

        # App A — create
        app_a, engine_a = _create_app(db_path)
        from app.modules.jobs.models import Job

        with Session(engine_a) as session:
            job = Job(tenant_id="t1", job_type="google_search")
            session.add(job)
            session.commit()
            job_id = job.id
        _dispose(engine_a)

        # App B — read
        app_b, engine_b = _create_app(db_path)
        with Session(engine_b) as session:
            restored = session.get(Job, job_id)
            assert restored is not None
            assert restored.tenant_id == "t1"
            assert restored.status == "queued"
        _dispose(engine_b)


def test_job_progress_survives_app_restart() -> None:
    """Write progress with App A, verify with App B."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "progress-test.db")

        app_a, engine_a = _create_app(db_path)
        from app.modules.jobs.models import Job

        with Session(engine_a) as session:
            job = Job(tenant_id="t1", job_type="google_search")
            session.add(job)
            session.commit()
            job_id = job.id
            job.status = "running"
            job.progress = 65
            job.progress_message = "Processing page 2"
            session.commit()
        _dispose(engine_a)

        app_b, engine_b = _create_app(db_path)
        with Session(engine_b) as session:
            restored = session.get(Job, job_id)
            assert restored is not None
            assert restored.status == "running"
            assert restored.progress == 65
            assert restored.progress_message == "Processing page 2"
        _dispose(engine_b)


def test_terminal_job_survives_app_restart() -> None:
    """A succeeded/failed job survives restart and won't re-execute."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "terminal-test.db")

        app_a, engine_a = _create_app(db_path)
        from app.modules.jobs.models import Job

        with Session(engine_a) as session:
            job = Job(
                tenant_id="t1",
                job_type="google_search",
                status="succeeded",
                progress=100,
                result_summary_json=json.dumps({"found": 5}),
            )
            session.add(job)
            session.commit()
            job_id = job.id
        _dispose(engine_a)

        app_b, engine_b = _create_app(db_path)
        with Session(engine_b) as session:
            restored = session.get(Job, job_id)
            assert restored is not None
            assert restored.status == "succeeded"
            assert restored.progress == 100

            # Worker would refuse to re-execute
            assert restored.status not in ("queued", "running")
            assert restored.status != "queued"
        _dispose(engine_b)


def test_worker_can_update_across_restart() -> None:
    """Simulate: web creates, worker updates, web reads back."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "worker-update.db")

        # Web creates
        app_w, engine_w = _create_app(db_path)
        from app.modules.jobs.models import Job
        from app.modules.jobs.repository import JobRepository

        with Session(engine_w) as session:
            repo = JobRepository(session)
            job = repo.create_for_tenant(Job(job_type="google_search"), tenant_id="t1")
            session.commit()
            job_id = job.id
        _dispose(engine_w)

        # Worker reads + updates
        app_r, engine_r = _create_app(db_path)
        with Session(engine_r) as session:
            job = session.get(Job, job_id)
            assert job is not None
            assert job.tenant_id == "t1"
            repo = JobRepository(session)
            repo.update_for_worker(job, tenant_id="t1", status="running", progress=50)
            session.commit()
        _dispose(engine_r)

        # Web reads back
        app_r2, engine_r2 = _create_app(db_path)
        with Session(engine_r2) as session:
            restored = session.get(Job, job_id)
            assert restored is not None
            assert restored.status == "running"
            assert restored.progress == 50
        _dispose(engine_r2)


def test_tenant_b_cannot_read_after_restart() -> None:
    """Tenant isolation survives app restart."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "isolation-restart.db")

        app_a, engine_a = _create_app(db_path)
        from app.modules.jobs.models import Job

        with Session(engine_a) as session:
            job = Job(tenant_id="t1", job_type="google_search")
            session.add(job)
            session.commit()
            job_id = job.id
        _dispose(engine_a)

        app_b, engine_b = _create_app(db_path)
        with Session(engine_b) as session:
            from app.modules.jobs.repository import JobRepository

            repo = JobRepository(session)
            assert repo.get_for_tenant(job_id, tenant_id="t1") is not None
            assert repo.get_for_tenant(job_id, tenant_id="t2") is None
        _dispose(engine_b)


def test_no_redis_or_memory_dependency(monkeypatch) -> None:
    """Job state is in SQLite, not Redis or in-memory dict."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "no-redis.db")
        app, engine = _create_app(db_path)

        from app.modules.jobs.models import Job

        with Session(engine) as session:
            job = Job(tenant_id="t1", job_type="google_search")
            session.add(job)
            session.commit()
            job_id = job.id

            # Set succeeded with result — no Redis involved
            job.status = "succeeded"
            job.progress = 100
            job.result_summary_json = json.dumps({"found": 10, "created": 8})
            session.commit()

        _dispose(engine)

        # New app, same file — state persisted
        app2, engine2 = _create_app(db_path)
        with Session(engine2) as session:
            restored = session.get(Job, job_id)
            assert restored is not None
            assert restored.status == "succeeded"
            assert json.loads(restored.result_summary_json)["found"] == 10
        _dispose(engine2)
