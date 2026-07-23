from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "test-tenant-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _seed(engine) -> tuple[str, str, str, str]:
    from app.modules.accounts.models import AdminUser, Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant_a = Tenant(company_name="Tenant A", industry="Export", status="active")
        tenant_b = Tenant(company_name="Tenant B", industry="Logistics", status="active")
        user_a = User(
            email="owner-a@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        user_b = User(
            email="owner-b@example.com",
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        admin = AdminUser(
            email="admin@example.com",
            password_hash=generate_password_hash("temporary-safe-password-123"),
            must_change_password=False,
        )
        session.add_all(
            [
                TenantMembership(tenant=tenant_a, user=user_a, role="owner"),
                TenantMembership(tenant=tenant_b, user=user_b, role="owner"),
                admin,
            ]
        )
        session.commit()
        return tenant_a.id, tenant_b.id, user_a.id, admin.id


def _tenant_session(client, *, tenant_id: str, user_id: str, auth_version: int = 1) -> None:
    with client.session_transaction() as sess:
        sess.clear()
        sess["tenant_id"] = tenant_id
        sess["user_id"] = user_id
        sess["auth_version"] = auth_version
        sess["tenant_email"] = "owner-a@example.com"


def _admin_session(client, *, admin_id: str, auth_version: int = 1) -> None:
    with client.session_transaction() as sess:
        sess.clear()
        sess["is_admin"] = True
        sess["admin_id"] = admin_id
        sess["admin_email"] = "admin@example.com"
        sess["admin_auth_version"] = auth_version


def test_system_diagnostics_requires_admin_session(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client = app.test_client()
    tenant_id, _tenant_b, user_id, admin_id = _seed(engine)

    unauthenticated = client.get("/admin/system")
    assert unauthenticated.status_code in {302, 303}
    assert unauthenticated.headers["Location"].endswith("/admin/login")

    _tenant_session(client, tenant_id=tenant_id, user_id=user_id)
    tenant_only = client.get("/admin/system")
    assert tenant_only.status_code in {302, 303}
    assert tenant_only.headers["Location"].endswith("/admin/login")

    _admin_session(client, admin_id=admin_id)
    admin = client.get("/admin/system")
    assert admin.status_code == 200
    assert b"System diagnostics" in admin.data


def test_audit_routes_respect_tenant_and_admin_boundaries(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client = app.test_client()
    tenant_a, tenant_b, user_id, admin_id = _seed(engine)

    from app.modules.audit.service import record_event

    with app.test_request_context("/", environ_base={"REMOTE_ADDR": "203.0.113.10"}):
        record_event(
            app,
            tenant_id=tenant_a,
            actor_user_id=user_id,
            action="tenant_a_only",
            target_type="lead",
            target_id="lead-a",
            safe_summary="Tenant A event",
        )
        record_event(
            app,
            tenant_id=tenant_b,
            actor_user_id="user-b",
            action="tenant_b_only",
            target_type="lead",
            target_id="lead-b",
            safe_summary="Tenant B event",
        )

    _tenant_session(client, tenant_id=tenant_a, user_id=user_id)
    tenant_response = client.get("/audit")
    html = tenant_response.get_data(as_text=True)
    assert tenant_response.status_code == 200
    assert "Tenant A event" in html
    assert "Tenant B event" not in html

    tenant_admin_audit = client.get("/admin/audit")
    assert tenant_admin_audit.status_code in {302, 303}
    assert tenant_admin_audit.headers["Location"].endswith("/admin/login")

    _admin_session(client, admin_id=admin_id)
    admin_response = client.get("/admin/audit")
    admin_html = admin_response.get_data(as_text=True)
    assert admin_response.status_code == 200
    assert "Tenant A event" in admin_html
    assert "Tenant B event" in admin_html


def test_settings_page_is_tenant_scoped(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    client = app.test_client()
    tenant_id, _tenant_b, user_id, _admin_id = _seed(engine)

    assert client.get("/settings").status_code in {302, 303}

    _tenant_session(client, tenant_id=tenant_id, user_id=user_id)
    response = client.get("/settings")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Tenant A" in html
    assert "Tenant B" not in html
    assert "CSRF enabled" in html


def test_error_pages_are_safe(monkeypatch) -> None:
    app, _engine = _app(monkeypatch)
    response = app.test_client().get("/missing-v2-06-route")
    html = response.get_data(as_text=True)

    assert response.status_code == 404
    assert "Page not found" in html
    assert "Traceback" not in html
    assert "SECRET_KEY" not in html


def test_audit_event_hashes_request_metadata(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, _tenant_b, user_id, _admin_id = _seed(engine)

    from app.modules.audit.models import AuditEvent
    from app.modules.audit.service import record_event

    with app.test_request_context(
        "/audit-source",
        environ_base={"REMOTE_ADDR": "198.51.100.77", "HTTP_USER_AGENT": "Sensitive UA"},
    ):
        record_event(
            app,
            tenant_id=tenant_id,
            actor_user_id=user_id,
            action="security_checked",
            safe_summary="Contains no secrets",
        )

    with Session(engine) as session:
        event = session.scalars(select(AuditEvent)).one()
        assert event.ip_hash
        assert event.user_agent_hash
        assert "198.51.100.77" not in event.ip_hash
        assert "Sensitive UA" not in event.user_agent_hash
        assert event.safe_summary == "Contains no secrets"
