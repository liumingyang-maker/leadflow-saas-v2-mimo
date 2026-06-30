"""Real CSRF protection tests for CRM write endpoints.

Uses development config (WTF_CSRF_ENABLED=True)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app.modules.accounts.models import Tenant, TenantMembership, User
from app.modules.leads.models import Lead


def _dev_client(monkeypatch):
    """Development-mode client with CSRF enabled and in-memory DB."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("development")
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    reset_engine_for_tests()
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        tenant = Tenant(company_name="Acme")
        user = User(
            email="owner@example.com",
            password_hash=generate_password_hash("pass1234"),
        )
        user.email_verified_at = datetime.now(UTC)
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()
        _tenant_id = tenant.id
        _user_id = user.id

    client = flask_app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = _tenant_id
        sess["user_id"] = _user_id
        sess["tenant_email"] = "owner@example.com"

    return client, engine, flask_app, _tenant_id


def _get_csrf(client) -> str:
    """Extract CSRF token from the /leads page."""
    from re import search

    html = client.get("/login").get_data(as_text=True)
    m = search(r'csrf_token" value="([^"]+)"', html)
    assert m is not None, "csrf_token not found"
    return m.group(1)


def _import_a_lead(client, engine, tenant_id) -> str:
    """Import a lead and return its ID."""
    from app.modules.leads.service import confirm_import

    confirm_import(
        client.application,
        tenant_id=tenant_id,
        filename="t.csv",
        content=b"email\ncsrf-test@x.com",
    )
    with Session(engine) as session:
        return session.scalars(select(Lead.id)).one()


def test_csrf_missing_on_import_preview_returns_400(monkeypatch) -> None:
    client, _engine, _app, _tid = _dev_client(monkeypatch)
    resp = client.post("/leads/import", data={"action": "preview"})
    assert resp.status_code == 400


def test_csrf_missing_on_stage_change_returns_400(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    resp = client.post(f"/leads/{lead_id}/stage", data={"stage": "qualified"})
    assert resp.status_code == 400


def test_csrf_missing_on_note_add_returns_400(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    resp = client.post(f"/leads/{lead_id}/note", data={"note": "test"})
    assert resp.status_code == 400


def test_csrf_missing_on_tag_add_returns_400(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    resp = client.post(f"/leads/{lead_id}/tag", data={"tag_name": "VIP"})
    assert resp.status_code == 400


def test_csrf_failure_does_not_write_to_db(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    client.post(f"/leads/{lead_id}/stage", data={"stage": "qualified"})
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        assert lead is not None
        assert lead.stage == "new"  # unchanged


def test_correct_csrf_token_succeeds(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    csrf = _get_csrf(client)
    resp = client.post(
        f"/leads/{lead_id}/stage",
        data={"stage": "qualified", "csrf_token": csrf},
    )
    assert resp.status_code in {302, 303}
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        assert lead is not None
        assert lead.stage == "qualified"


def test_wrong_csrf_token_returns_400(monkeypatch) -> None:
    client, engine, app, tid = _dev_client(monkeypatch)
    lead_id = _import_a_lead(client, engine, tid)
    resp = client.post(
        f"/leads/{lead_id}/stage",
        data={"stage": "qualified", "csrf_token": "bad-token"},
    )
    assert resp.status_code == 400
