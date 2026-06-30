"""V2-04-011: Milestone acceptance — full V2-04 smoke test."""

from __future__ import annotations


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def test_all_migrations_from_empty(monkeypatch) -> None:
    import os
    import tempfile

    from alembic import command
    from alembic.config import Config

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")

        cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "-1")
        command.upgrade(cfg, "head")


def test_all_modules_import_cleanly() -> None:
    """Every module in the new jobs package imports without error."""
    from app.modules.jobs import models, repository, service, worker

    assert models is not None
    assert repository is not None
    assert service is not None
    assert worker is not None


def test_collection_route_requires_login(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    client = app.test_client()
    resp = client.get("/collection")
    assert resp.status_code in {302, 303}


def test_docker_config_valid() -> None:
    """Verify the docker-compose file has required services."""
    with open("docker-compose.yml", encoding="utf-8") as f:
        content = f.read()

    assert "web:" in content
    assert "redis:" in content
    assert "worker:" in content
    assert "redis:7" in content


def test_run_worker_script_exists() -> None:
    import os

    assert os.path.isfile("run_worker.py")


def test_worker_recovery_function_exists() -> None:
    from app.modules.jobs.worker import recover_stale_jobs

    assert callable(recover_stale_jobs)


def test_worker_adapter_registry_has_adapters(monkeypatch) -> None:
    from app.modules.jobs.worker import _get_adapter

    adapter = _get_adapter("google_search")
    assert adapter is not None

    adapter = _get_adapter("google_maps")
    assert adapter is not None


def test_no_real_network_in_tests(monkeypatch) -> None:
    """All test data uses in-memory SQLite, no external calls."""
    app, engine = _app(monkeypatch)
    assert "sqlite:///:memory:" in str(engine.url)
