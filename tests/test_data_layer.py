from __future__ import annotations

import importlib
import socket
import threading

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import inspect, text


def test_create_app_configures_database_uri_for_testing(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app

    flask_app = create_app("testing")

    assert flask_app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"
    assert flask_app.config["SQLALCHEMY_ENGINE_OPTIONS"]["future"] is True


def test_database_engine_is_initialized_lazily(monkeypatch) -> None:
    import app.extensions as extensions

    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    extensions.reset_engine_for_tests()

    from app import create_app
    from app.extensions import get_engine

    flask_app = create_app("testing")

    assert extensions.engine_is_initialized() is False
    engine = get_engine(flask_app)
    assert extensions.engine_is_initialized() is True

    with engine.connect() as connection:
        assert connection.execute(text("select 1")).scalar_one() == 1

    extensions.reset_engine_for_tests()


def test_database_engine_recreates_when_database_uri_changes() -> None:
    import app.extensions as extensions

    extensions.reset_engine_for_tests()
    first = extensions.get_engine(database_uri="sqlite:///:memory:")
    second = extensions.get_engine(database_uri="sqlite:///changed.db")

    try:
        assert first is not second
        assert str(second.url).endswith("changed.db")
    finally:
        extensions.reset_engine_for_tests()


def test_imports_do_not_start_database_or_network_side_effects(monkeypatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("data layer imports must not start background or network work")

    monkeypatch.setattr(threading.Thread, "start", fail)
    monkeypatch.setattr(threading.Timer, "start", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)

    module = importlib.import_module("app.extensions")

    assert module.engine_is_initialized() is False


def test_alembic_upgrade_head_runs_against_sqlite(tmp_path) -> None:
    db_path = tmp_path / "leadflow-v2.db"
    cfg = AlembicConfig("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")

    command.upgrade(cfg, "head")

    from app.extensions import get_engine

    engine = get_engine(database_uri=f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "alembic_version" in inspector.get_table_names()
    finally:
        engine.dispose()
