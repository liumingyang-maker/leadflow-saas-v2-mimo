from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    Base.metadata.create_all(get_engine(flask_app))
    return flask_app.test_client()


def test_login_placeholder_renders_signal_workspace_form(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch).get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Sign in to LeadFlow" in html
    assert 'for="email"' in html
    assert 'for="password"' in html
    assert 'type="password"' in html
    assert 'method="post" action="/login"' in html
    assert "Create a tenant" in html
    assert '<a class="lf-skip-link" href="#main">' in html


def test_workbench_shell_renders_primary_information_architecture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import Session

    from app.extensions import get_engine
    from app.modules.accounts.models import Tenant, User

    client = _client(monkeypatch)
    engine = get_engine(database_uri="sqlite:///:memory:")
    with Session(engine) as session:
        tenant = Tenant(company_name="Acme Export")
        session.add(tenant)
        session.commit()
        tenant_id = tenant.id
        user = User(
            email="shell@example.com",
            password_hash="pbkdf2:sha256:1$fake",
            email_verified_at=None,
        )
        session.add(user)
        session.commit()
        user_id = user.id
    with client.session_transaction() as session_data:
        session_data["tenant_id"] = tenant_id
        session_data["user_id"] = user_id

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for nav in ["Workbench", "Find customers", "Lead review", "CRM", "Outreach", "Settings"]:
        assert nav in html
    for state in ["Loading current tasks", "No reviewed leads yet", "Unable to load pipeline"]:
        assert state in html
    assert 'aria-current="page"' in html
    assert 'aria-label="Primary navigation"' in html


def test_component_primitives_include_expected_macros() -> None:
    component_dir = ROOT / "app" / "templates" / "components"
    for name in [
        "_tables.html",
        "_jobs.html",
        "_alerts.html",
        "_dialogs.html",
        "_stats.html",
    ]:
        assert (component_dir / name).is_file()


def test_app_shell_css_supports_mobile_and_accessible_targets() -> None:
    css = (ROOT / "app" / "static" / "css" / "components.css").read_text(encoding="utf-8")

    assert "@media (max-width: 767px)" in css
    assert "min-height: 40px" in css
    assert ".lf-table-wrap {\n  overflow-x: auto;" in css
