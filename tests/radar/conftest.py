from __future__ import annotations

import pytest


@pytest.fixture
def radar_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.delenv("COMPETITOR_RADAR_ENABLED", raising=False)

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    Base.metadata.create_all(get_engine(app))
    yield app
    reset_engine_for_tests()
