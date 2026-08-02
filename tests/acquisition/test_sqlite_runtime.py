from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import UTC, datetime
from threading import Barrier, Event, Lock
from time import monotonic
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def isolated_engine():
    from app.extensions import reset_engine_for_tests

    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


def test_file_sqlite_enables_wal_and_default_busy_timeout(tmp_path):
    from app.extensions import get_engine

    engine = get_engine(database_uri=f"sqlite:///{tmp_path / 'runtime.db'}")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() == "wal"
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 5000


def test_file_sqlite_uses_validated_app_busy_timeout(tmp_path):
    from app.extensions import get_engine

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'custom-timeout.db'}",
        SQLALCHEMY_ENGINE_OPTIONS={"future": True},
        SQLITE_BUSY_TIMEOUT_MS=1234,
    )

    with get_engine(app).connect() as connection:
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 1234


@pytest.mark.parametrize("value", ["not-an-integer", 999, 30001, "5000; PRAGMA trusted_schema=ON"])
def test_file_sqlite_rejects_unsafe_busy_timeout_before_connect(tmp_path, value):
    from app.extensions import get_engine

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'invalid-timeout.db'}",
        SQLALCHEMY_ENGINE_OPTIONS={"future": True},
        SQLITE_BUSY_TIMEOUT_MS=value,
    )

    with pytest.raises(RuntimeError, match="SQLITE_BUSY_TIMEOUT_MS"):
        get_engine(app)


def test_busy_timeout_config_accepts_only_bounded_integers(monkeypatch):
    from app.config import TestingConfig, resolve_config

    monkeypatch.setattr(
        TestingConfig,
        "SQLALCHEMY_DATABASE_URI",
        "sqlite:///runtime-config.db",
    )

    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "1000")
    assert resolve_config("testing").SQLITE_BUSY_TIMEOUT_MS == 1000

    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "30000")
    assert resolve_config("testing").SQLITE_BUSY_TIMEOUT_MS == 30000

    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "999")
    with pytest.raises(RuntimeError, match="between 1000 and 30000"):
        resolve_config("testing")


@pytest.mark.parametrize(
    "database_uri",
    [
        "sqlite:///:memory:",
        "postgresql://user:password@db.example/leadflow",
    ],
)
def test_non_file_config_does_not_parse_sqlite_timeout(monkeypatch, database_uri):
    from app.config import TestingConfig, resolve_config

    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", database_uri)
    monkeypatch.setenv("SQLITE_BUSY_TIMEOUT_MS", "not-an-integer")

    assert resolve_config("testing") is TestingConfig


def test_memory_sqlite_does_not_enable_wal():
    from app.extensions import get_engine

    engine = get_engine(database_uri="sqlite+pysqlite:///:memory:")

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() != "wal"


def test_memory_sqlite_does_not_parse_sqlite_timeout():
    from app.extensions import get_engine

    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:",
        SQLALCHEMY_ENGINE_OPTIONS={"future": True},
        SQLITE_BUSY_TIMEOUT_MS="not-an-integer",
    )

    with get_engine(app).connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one().lower() != "wal"


@pytest.mark.parametrize(
    ("dialect_name", "url", "expected"),
    [
        ("sqlite", "sqlite:///runtime.db", True),
        ("sqlite", "sqlite:////var/lib/leadflow/runtime.db", True),
        ("sqlite", "sqlite+pysqlite:///runtime.db", True),
        ("sqlite", "sqlite:///:memory:", False),
        (
            "sqlite",
            "sqlite+pysqlite:///file:named?mode=memory&cache=shared&uri=true",
            False,
        ),
        ("sqlite", "sqlite+pysqlite:///file::memory:?cache=shared&uri=true", False),
        ("sqlite", "sqlite+pysqlite:///file:named?mode=memory&cache=shared", True),
        (
            "sqlite",
            "sqlite+pysqlite:///file:named?mode=memory&cache=shared&uri=false",
            True,
        ),
        ("sqlite", "sqlite+pysqlite:///file::memory:?cache=shared&uri=false", True),
        ("postgresql", "postgresql://user:password@db.example/leadflow", False),
    ],
)
def test_file_sqlite_predicate_requires_a_file_database(dialect_name, url, expected):
    from app.extensions import _is_file_sqlite

    shaped_engine = SimpleNamespace(
        dialect=SimpleNamespace(name=dialect_name),
        url=make_url(url),
    )

    assert _is_file_sqlite(shaped_engine) is expected


def test_postgres_engine_does_not_parse_or_cache_sqlite_timeout(monkeypatch):
    import app.extensions as extensions

    created = []

    def fake_create_engine(uri, **_options):
        engine = SimpleNamespace(
            dialect=SimpleNamespace(name="postgresql"),
            url=make_url(uri),
            dispose=lambda: None,
        )
        created.append(engine)
        return engine

    monkeypatch.setattr(extensions, "create_engine", fake_create_engine)
    app = Flask(__name__)
    app.config.update(
        SQLALCHEMY_DATABASE_URI="postgresql://user:password@db.example/leadflow",
        SQLALCHEMY_ENGINE_OPTIONS={"future": True},
        SQLITE_BUSY_TIMEOUT_MS="not-an-integer",
    )

    first = extensions.get_engine(app)
    app.config["SQLITE_BUSY_TIMEOUT_MS"] = "still-not-an-integer"
    second = extensions.get_engine(app)

    assert first is second
    assert created == [first]


def test_concurrent_initialization_returns_one_engine(tmp_path, monkeypatch):
    import app.extensions as extensions

    real_create_engine = extensions.create_engine
    first_create_entered = Event()
    release_first_create = Event()
    second_create_entered = Event()
    created = []
    create_lock = Lock()

    def slow_create_engine(uri, **options):
        with create_lock:
            call_number = len(created) + 1
            created.append(None)
        if call_number == 1:
            first_create_entered.set()
            if not release_first_create.wait(timeout=5):
                raise AssertionError("first engine initialization was not released")
        else:
            second_create_entered.set()
        engine = real_create_engine(uri, **options)
        with create_lock:
            created[call_number - 1] = engine
        return engine

    monkeypatch.setattr(extensions, "create_engine", slow_create_engine)
    database_uri = f"sqlite:///{tmp_path / 'single-engine.db'}"
    executor = ThreadPoolExecutor(max_workers=2)
    futures = []
    try:
        futures.append(executor.submit(extensions.get_engine, database_uri=database_uri))
        assert first_create_entered.wait(timeout=5)
        futures.append(executor.submit(extensions.get_engine, database_uri=database_uri))
        second_create_entered.wait(timeout=0.2)
        release_first_create.set()
        engines = [future.result(timeout=5) for future in futures]
    finally:
        release_first_create.set()
        executor.shutdown(wait=True, cancel_futures=True)
        for engine in created:
            if engine is not None:
                engine.dispose()

    assert engines[0] is engines[1]
    assert len(created) == 1


def test_file_sqlite_supports_bounded_web_and_reconciler_writes(tmp_path, caplog):
    from app import create_app
    from app.extensions import Base, get_engine
    from app.modules.acquisition.jobs import reconcile_missions
    from app.modules.acquisition.models import (
        AcquisitionCandidate,
        AcquisitionMission,
        Notification,
        ProductKnowledgeSnapshot,
    )
    from app.modules.acquisition.service import create_product_snapshot
    from app.modules.jobs.models import Job

    database_uri = f"sqlite:///{tmp_path / 'concurrent.db'}"
    app = create_app("testing")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=database_uri,
        SQLITE_BUSY_TIMEOUT_MS=5000,
    )
    engine = get_engine(app)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        product = ProductKnowledgeSnapshot(
            tenant_id="reconcile-tenant",
            version="v1",
            product_name="Existing engine",
            summary="Existing motorcycle engine",
            facts_json='[{"name":"product","value":"engine"}]',
            prohibited_claims_json="[]",
            content_hash="a" * 64,
            approved_by="owner",
        )
        session.add(product)
        session.flush()
        mission = AcquisitionMission(
            tenant_id="reconcile-tenant",
            name="Completed research",
            status="running",
            product_snapshot_id=product.id,
            created_by="owner",
        )
        session.add(mission)
        session.flush()
        candidate = AcquisitionCandidate(
            tenant_id="reconcile-tenant",
            mission_id=mission.id,
            status="eligible",
            company_name="Visible candidate",
            dedupe_key="domain:visible.example",
        )
        session.add(candidate)
        session.add(
            Job(
                tenant_id="reconcile-tenant",
                job_type="candidate_assess",
                status="succeeded",
                progress=100,
                payload_json=json.dumps({"mission_id": mission.id, "candidate_id": candidate.id}),
            )
        )
        session.commit()
        mission_id = mission.id

    start = Barrier(2)
    web_write_holds_lock = Event()
    reconciler_attempted_write = Event()

    def hold_web_write_lock(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("INSERT INTO PRODUCT_KNOWLEDGE_SNAPSHOTS"):
            web_write_holds_lock.set()
            if not reconciler_attempted_write.wait(timeout=5):
                raise AssertionError("reconciler did not attempt a write while Web held the lock")

    def detect_reconciler_write(
        _connection,
        _cursor,
        statement,
        _parameters,
        _context,
        _executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("UPDATE ACQUISITION_MISSIONS"):
            if not web_write_holds_lock.wait(timeout=5):
                raise AssertionError("Web did not acquire the write lock before reconciliation")
            reconciler_attempted_write.set()

    event.listen(engine, "after_cursor_execute", hold_web_write_lock)
    event.listen(engine, "before_cursor_execute", detect_reconciler_write)
    overlap_observed = False

    def web_service_write() -> str:
        start.wait(timeout=10)
        snapshot = create_product_snapshot(
            app,
            tenant_id="web-tenant",
            actor_id="owner",
            product_name="Concurrent engine",
            summary="A concurrent service write",
            facts=[{"name": "product", "value": "engine"}],
            prohibited_claims=[],
        )
        return snapshot.id

    def acquisition_reconciler_write() -> int:
        start.wait(timeout=10)
        return reconcile_missions(
            app,
            tenant_id="reconcile-tenant",
            now=datetime.now(UTC),
        )

    executor = ThreadPoolExecutor(max_workers=2)
    futures = set()
    started_at = monotonic()
    try:
        futures = {
            executor.submit(web_service_write),
            executor.submit(acquisition_reconciler_write),
        }
        done, not_done = wait(futures, timeout=10)
        assert not not_done, "concurrent SQLite writes exceeded the 10 second bound"
        for future in done:
            error = future.exception()
            assert not isinstance(error, OperationalError)
            if error is not None:
                raise error
        overlap_observed = web_write_holds_lock.is_set() and reconciler_attempted_write.is_set()
    finally:
        web_write_holds_lock.set()
        reconciler_attempted_write.set()
        start.abort()
        executor.shutdown(wait=True, cancel_futures=True)
        event.remove(engine, "after_cursor_execute", hold_web_write_lock)
        event.remove(engine, "before_cursor_execute", detect_reconciler_write)

    assert overlap_observed
    assert monotonic() - started_at < 10

    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(ProductKnowledgeSnapshot)
                .where(ProductKnowledgeSnapshot.tenant_id == "web-tenant")
            )
            == 1
        )
        reconciled = session.get(AcquisitionMission, mission_id)
        assert reconciled is not None
        assert reconciled.status == "completed"
        assert (
            session.scalar(
                select(func.count())
                .select_from(Notification)
                .where(Notification.tenant_id == "reconcile-tenant")
            )
            == 1
        )

    assert "database is locked" not in caplog.text.lower()
