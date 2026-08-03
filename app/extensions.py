from __future__ import annotations

from threading import RLock
from typing import Any

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

from app.config import _is_file_sqlite_uri

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


_engine: Engine | None = None
_engine_uri: str | None = None
_engine_busy_timeout_ms: int | None = None
_engine_lock = RLock()
csrf = CSRFProtect()


def init_extensions(app: Flask) -> None:
    app.extensions["sqlalchemy_metadata"] = Base.metadata
    csrf.init_app(app)


def get_engine(app: Flask | None = None, *, database_uri: str | None = None) -> Engine:
    global _engine, _engine_busy_timeout_ms, _engine_uri
    uri = database_uri or _database_uri_from_app(app)
    is_file_sqlite = _is_file_sqlite_uri(uri)
    busy_timeout_ms = _busy_timeout_from_app(app) if is_file_sqlite else None
    with _engine_lock:
        if _engine is None or _engine_uri != uri or _engine_busy_timeout_ms != busy_timeout_ms:
            if _engine is not None:
                _engine.dispose()
            options = _engine_options_from_app(app)
            _engine = create_engine(uri, **options)
            if busy_timeout_ms is not None:
                _configure_file_sqlite(_engine, busy_timeout_ms=busy_timeout_ms)
            _engine_uri = uri
            _engine_busy_timeout_ms = busy_timeout_ms
        return _engine


def engine_is_initialized() -> bool:
    with _engine_lock:
        return _engine is not None


def reset_engine_for_tests() -> None:
    global _engine, _engine_busy_timeout_ms, _engine_uri
    with _engine_lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_uri = None
        _engine_busy_timeout_ms = None


def _is_file_sqlite(engine: Engine) -> bool:
    return engine.dialect.name == "sqlite" and _is_file_sqlite_uri(engine.url)


def _configure_file_sqlite(engine: Engine, *, busy_timeout_ms: int) -> None:
    if not _is_file_sqlite(engine):
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
            cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()


def _database_uri_from_app(app: Flask | None) -> str:
    if app is None:
        raise RuntimeError("database_uri or app is required to initialize the SQLAlchemy engine")
    return str(app.config["SQLALCHEMY_DATABASE_URI"])


def _engine_options_from_app(app: Flask | None) -> dict[str, Any]:
    if app is None:
        return {"future": True}
    return dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {"future": True}))


def _busy_timeout_from_app(app: Flask | None) -> int:
    raw: object = 5000 if app is None else app.config.get("SQLITE_BUSY_TIMEOUT_MS", 5000)
    if isinstance(raw, bool) or not isinstance(raw, (int, str)):
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be an integer")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be an integer") from exc
    if value < 1000 or value > 30000:
        raise RuntimeError("SQLITE_BUSY_TIMEOUT_MS must be between 1000 and 30000")
    return value


import app.modules.accounts.models  # noqa: E402,F401
import app.modules.accounts.payment_models  # noqa: E402,F401
import app.modules.acquisition.models  # noqa: E402,F401
import app.modules.audit.models  # noqa: E402,F401
import app.integrations.browser.models  # noqa: E402,F401
import app.modules.inbound.models  # noqa: E402,F401
import app.modules.jobs.models  # noqa: E402,F401
import app.modules.leads.models  # noqa: E402,F401
import app.modules.outreach.models  # noqa: E402,F401
