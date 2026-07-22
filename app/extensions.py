from __future__ import annotations

from typing import Any

from flask import Flask
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

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
csrf = CSRFProtect()


def init_extensions(app: Flask) -> None:
    app.extensions["sqlalchemy_metadata"] = Base.metadata
    csrf.init_app(app)


def get_engine(app: Flask | None = None, *, database_uri: str | None = None) -> Engine:
    global _engine, _engine_uri
    uri = database_uri or _database_uri_from_app(app)
    if _engine is None or _engine_uri != uri:
        if _engine is not None:
            _engine.dispose()
        options = _engine_options_from_app(app)
        _engine = create_engine(uri, **options)
        _engine_uri = uri
    return _engine


def engine_is_initialized() -> bool:
    return _engine is not None


def reset_engine_for_tests() -> None:
    global _engine, _engine_uri
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _engine_uri = None


def _database_uri_from_app(app: Flask | None) -> str:
    if app is None:
        raise RuntimeError("database_uri or app is required to initialize the SQLAlchemy engine")
    return str(app.config["SQLALCHEMY_DATABASE_URI"])


def _engine_options_from_app(app: Flask | None) -> dict[str, Any]:
    if app is None:
        return {"future": True}
    return dict(app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {"future": True}))


import app.modules.accounts.models  # noqa: E402,F401
import app.modules.accounts.payment_models  # noqa: E402,F401
import app.modules.audit.models  # noqa: E402,F401
import app.modules.inbound.models  # noqa: E402,F401
import app.modules.jobs.models  # noqa: E402,F401
import app.modules.leads.models  # noqa: E402,F401
import app.modules.outreach.models  # noqa: E402,F401
