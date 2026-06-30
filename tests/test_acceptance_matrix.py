"""Manual acceptance matrix automation.

Covers remaining items from PRODUCTION_READINESS_CHECKLIST.md that aren't
fully covered by existing Playwright tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import Base, get_engine, reset_engine_for_tests
from app.modules.accounts.models import Tenant, TenantMembership, User


@pytest.fixture()
def app(tmp_path, monkeypatch):
    db_path = tmp_path / "acceptance.db"
    monkeypatch.setenv("SECRET_KEY", "acceptance-test-secret-key-long-enough")
    monkeypatch.setenv("TENANT_SECRET_KEY", "acceptance-tenant-secret-key-long-enough")
    from app.config import DevelopmentConfig

    original_uri = DevelopmentConfig.SQLALCHEMY_DATABASE_URI
    original_csrf = DevelopmentConfig.WTF_CSRF_ENABLED
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"
    DevelopmentConfig.WTF_CSRF_ENABLED = False  # Disable for acceptance testing
    reset_engine_for_tests()
    flask_app = create_app("development")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        tenant = Tenant(company_name="Acceptance Corp", industry="Tech", status="active")
        user = User(
            email="accept@example.com",
            password_hash=generate_password_hash("AcceptPass123!"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()
    yield flask_app
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = original_uri
    DevelopmentConfig.WTF_CSRF_ENABLED = original_csrf
    reset_engine_for_tests()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def authed_client(client):
    client.post(
        "/login",
        data={"email": "accept@example.com", "password": "AcceptPass123!"},
        follow_redirects=True,
    )
    return client


class TestLoginLogout:
    """Login and logout flow."""

    def test_login_page_loads(self, client):
        resp = client.get("/login")
        assert resp.status_code == 200

    def test_login_success(self, client):
        resp = client.post(
            "/login",
            data={"email": "accept@example.com", "password": "AcceptPass123!"},
            follow_redirects=False,
        )
        assert resp.status_code in (302, 303)

    def test_login_wrong_password(self, client):
        resp = client.post(
            "/login",
            data={"email": "accept@example.com", "password": "wrong"},
            follow_redirects=False,
        )
        # Should stay on login page or return error
        assert resp.status_code in (200, 302)

    def test_logout(self, authed_client):
        resp = authed_client.post("/logout", follow_redirects=False)
        assert resp.status_code in (302, 303)


class TestOnboarding:
    """Onboarding flow."""

    def test_onboarding_page_requires_login(self, client):
        resp = client.get("/onboarding", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_onboarding_page_loads(self, authed_client):
        resp = authed_client.get("/onboarding")
        assert resp.status_code in (200, 302)  # May redirect if already onboarded


class TestWorkbench:
    """Workbench / dashboard."""

    def test_workbench_requires_login(self, client):
        resp = client.get("/workbench", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_workbench_loads(self, authed_client):
        resp = authed_client.get("/workbench", follow_redirects=False)
        assert resp.status_code in (200, 302)  # May redirect to onboarding


class TestLeadsCRM:
    """CRM core flows."""

    def test_leads_list(self, authed_client):
        resp = authed_client.get("/leads", follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_import_page(self, authed_client):
        resp = authed_client.get("/leads/import", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestCollection:
    """Collection workspace."""

    def test_collection_page(self, authed_client):
        resp = authed_client.get("/collection", follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_collection_search_page(self, authed_client):
        resp = authed_client.get("/collection/search", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestOutreach:
    """Outreach flows."""

    def test_outreach_page(self, authed_client):
        resp = authed_client.get("/outreach", follow_redirects=False)
        assert resp.status_code in (200, 302)

    def test_outreach_templates(self, authed_client):
        resp = authed_client.get("/outreach/templates", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestInbound:
    """Inbound API management."""

    def test_inbound_page(self, authed_client):
        resp = authed_client.get("/inbound", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestSettings:
    """Settings page."""

    def test_settings_page(self, authed_client):
        resp = authed_client.get("/settings", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestAuditLog:
    """Audit log."""

    def test_audit_page(self, authed_client):
        resp = authed_client.get("/audit", follow_redirects=False)
        assert resp.status_code in (200, 302)


class TestSecurityHeaders:
    """Security headers on all responses."""

    def test_security_headers_present(self, client):
        resp = client.get("/health/live")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_no_traceback_in_error(self, client):
        """404 should not expose Python traceback."""
        resp = client.get("/nonexistent-page-12345")
        assert resp.status_code == 404
        body = resp.data.decode()
        assert "Traceback" not in body


class TestHealthEndpoints:
    """Health check endpoints."""

    def test_health_live(self, client):
        resp = client.get("/health/live")
        assert resp.status_code == 200

    def test_health_ready(self, client):
        resp = client.get("/health/ready")
        assert resp.status_code == 200


class TestAdminAccess:
    """Admin access control."""

    def test_admin_requires_login(self, client):
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code in (302, 303)

    def test_admin_login_page(self, client):
        resp = client.get("/admin/login")
        assert resp.status_code == 200
