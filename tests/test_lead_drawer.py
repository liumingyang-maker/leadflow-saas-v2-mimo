"""Tests for the HTMX lead detail drawer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _client(monkeypatch):
    app, engine = _app(monkeypatch)
    return app.test_client(), engine, app


def test_drawer_route_returns_partial(monkeypatch) -> None:
    client, _engine, app, tid, lead_id = _setup(monkeypatch)
    resp = client.get(f"/leads/{lead_id}/drawer")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<!doctype html>" not in html.lower()
    assert "lf-drawer-inner" in html


def test_drawer_shows_lead_info(monkeypatch) -> None:
    client, _engine, app, tid, lead_id = _setup(monkeypatch)
    resp = client.get(f"/leads/{lead_id}/drawer")
    html = resp.get_data(as_text=True)
    assert "lead@test.com" in html
    assert "TestLead" in html


def test_full_detail_page_still_works(monkeypatch) -> None:
    client, _engine, app, tid, lead_id = _setup(monkeypatch)
    resp = client.get(f"/leads/{lead_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "<!doctype html>" in html.lower()
    assert "lead@test.com" in html


def test_cross_tenant_drawer_returns_404(monkeypatch) -> None:
    """A user from tenant B cannot open tenant A's lead drawer."""
    client, engine, app, tid, lead_id = _setup(monkeypatch)
    # Login as a different tenant user
    from datetime import UTC, datetime

    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        other_tenant = Tenant(company_name="Other")
        from werkzeug.security import generate_password_hash

        other_user = User(email="other@x.com", password_hash=generate_password_hash("pass"))
        other_user.email_verified_at = datetime.now(UTC)
        session.add(TenantMembership(tenant=other_tenant, user=other_user, role="owner"))
        session.commit()
        _other_tid = other_tenant.id
        _other_uid = other_user.id

    with client.session_transaction() as sess:
        sess["tenant_id"] = _other_tid
        sess["user_id"] = _other_uid
        sess["tenant_email"] = other_user.email

    resp = client.get(f"/leads/{lead_id}/drawer")
    assert resp.status_code == 404


def test_drawer_list_link_has_htmx_attributes(monkeypatch) -> None:
    client, _engine, app, tid, lead_id = _setup(monkeypatch)
    resp = client.get("/leads")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'hx-get="/leads/' in html
    assert 'hx-target="#lead-drawer-content"' in html


def test_xss_prevention_in_drawer(monkeypatch) -> None:
    """Malicious strings in lead data should be HTML-escaped in the drawer."""
    client, engine, app, tid, lead_id = _setup_with_malicious(monkeypatch)
    resp = client.get(f"/leads/{lead_id}/drawer")
    html = resp.get_data(as_text=True).lower()
    assert "&lt;script&gt;" in html or "<script>" not in html
    assert "onmouseover" not in html


def test_unsafe_website_does_not_render_clickable_javascript_href(monkeypatch) -> None:
    client, _engine, _app, _tid, lead_id = _setup_with_malicious_website(monkeypatch)

    response = client.get(f"/leads/{lead_id}")
    html = response.get_data(as_text=True).lower()

    assert response.status_code == 200
    assert 'href="javascript:' not in html
    assert "javascript:alert(1)" in html


def test_safe_website_still_renders_clickable_http_href(monkeypatch) -> None:
    client, _engine, _app, _tid, lead_id = _setup_with_website(monkeypatch, "https://example.com")

    response = client.get(f"/leads/{lead_id}")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'href="https://example.com"' in html


def test_drawer_has_no_safe_or_markup(monkeypatch) -> None:
    """The drawer partial template contains no |safe."""
    import os

    path = os.path.join(
        os.path.dirname(__file__), "..", "app", "templates", "leads", "_drawer.html"
    )
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "|safe" not in content


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _setup(monkeypatch):
    """Return (client, engine, app, tenant_id, lead_id)."""
    client, engine, app = _client(monkeypatch)
    tid = _register_and_login(client, engine)
    from app.modules.leads.service import confirm_import

    confirm_import(
        app, tenant_id=tid, filename="t.csv", content=b"email,first_name\nlead@test.com,TestLead"
    )
    from app.modules.leads.models import Lead

    with Session(engine) as session:
        lead_id = session.scalars(select(Lead.id)).one()
    return client, engine, app, tid, lead_id


def _setup_with_malicious(monkeypatch):
    """Return (client, engine, app, tenant_id, lead_id) with XSS data."""
    monkeypatch.setenv("SECRET_KEY", "test-key")
    import app as app_module
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = app_module.create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)

    client = flask_app.test_client()
    tid = _register_and_login(client, engine)

    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(
            Lead(
                tenant_id=tid,
                email="<script>alert(1)</script>@x.com",
                notes='<img src=x onerror=fetch("http://evil")>',
            ),
            tenant_id=tid,
        )
        session.commit()
        lead_id = lead.id

    return client, engine, flask_app, tid, lead_id


def _setup_with_malicious_website(monkeypatch):
    return _setup_with_website(monkeypatch, "javascript:alert(1)")


def _setup_with_website(monkeypatch, website: str):
    """Return (client, engine, app, tenant_id, lead_id) with lead website."""
    client, engine, flask_app = _client(monkeypatch)
    tid = _register_and_login(client, engine)

    from app.modules.leads.models import Lead
    from app.modules.leads.repository import LeadRepository

    with Session(engine) as session:
        repo = LeadRepository(session)
        lead = repo.add(
            Lead(
                tenant_id=tid,
                email="website@example.com",
                website=website,
            ),
            tenant_id=tid,
        )
        session.commit()
        lead_id = lead.id

    return client, engine, flask_app, tid, lead_id


def _register_and_login(client, engine) -> str:
    from app.modules.accounts.models import EmailToken, Tenant

    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
        },
    )
    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
        tenant_id = session.scalars(select(Tenant.id)).one()
    client.get(f"/verify-email/{token}")
    client.post("/login", data={"email": "owner@example.com", "password": "safe-password-123"})
    return tenant_id
