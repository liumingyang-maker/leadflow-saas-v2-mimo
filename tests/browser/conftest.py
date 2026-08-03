from __future__ import annotations

import pytest
from sqlalchemy.orm import Session


@pytest.fixture
def browser_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("DEPLOYMENT_MODE", "internal")
    monkeypatch.setenv("BROWSER_RESEARCH_ENABLED", "true")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    app = create_app("testing")
    Base.metadata.create_all(get_engine(app))
    yield app
    reset_engine_for_tests()


@pytest.fixture
def db_session(browser_app):
    from app.extensions import get_engine

    with Session(get_engine(browser_app)) as session:
        yield session


@pytest.fixture
def approved_policy(browser_app, db_session):
    from app.integrations.browser.models import BrowserSitePolicy

    policy = BrowserSitePolicy(
        tenant_id="t1",
        canonical_domain="example.com",
        access_mode="auto_public",
        terms_status="approved",
        robots_status="allowed",
        allowed_origins_json='["https://example.com"]',
        allowed_paths_json='["/"]',
        approved_by="user-1",
    )
    db_session.add(policy)
    db_session.commit()
    return policy
