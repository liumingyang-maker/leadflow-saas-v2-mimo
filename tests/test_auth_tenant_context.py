from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash


def _app(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "auth-tenant-test-secret-key-that-is-long-enough")
    monkeypatch.setenv(
        "TENANT_SECRET_KEY", "auth-tenant-test-tenant-secret-key-that-is-long-enough"
    )
    monkeypatch.setenv("OUTREACH_SIGNING_KEY", "auth-tenant-test-outreach-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app, engine


def _seed_user_with_tenant(
    engine,
    *,
    email: str = "owner@example.com",
    company: str = "Export Co",
) -> tuple[str, str]:
    from app.modules.accounts.models import Tenant, TenantMembership, User

    with Session(engine) as session:
        tenant = Tenant(company_name=company, status="active", plan="basic")
        user = User(
            email=email,
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(TenantMembership(tenant=tenant, user=user, role="owner"))
        session.commit()
        return tenant.id, user.id


def _seed_user_without_tenant(engine, *, email: str = "orphan@example.com") -> str:
    from app.modules.accounts.models import User

    with Session(engine) as session:
        user = User(
            email=email,
            password_hash=generate_password_hash("safe-password-123"),
            email_verified_at=datetime.now(UTC),
        )
        session.add(user)
        session.commit()
        return user.id


def _seed_tenant(engine, *, company: str = "Other Co") -> str:
    from app.modules.accounts.models import Tenant

    with Session(engine) as session:
        tenant = Tenant(company_name=company, status="active", plan="basic")
        session.add(tenant)
        session.commit()
        return tenant.id


def test_fresh_login_sets_tenant_context_and_workbench_is_available(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    client = app.test_client()

    response = client.post(
        "/login",
        data={"email": "owner@example.com", "password": "safe-password-123"},
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/workbench")
    with client.session_transaction() as sess:
        assert sess["tenant_id"] == tenant_id
        assert sess["user_id"] == user_id
    workbench = client.get("/workbench")
    assert workbench.status_code == 200


def test_authenticated_request_recovers_missing_tenant_id(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["tenant_email"] = "owner@example.com"

    response = client.get("/workbench")

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["tenant_id"] == tenant_id


def test_authenticated_request_replaces_stale_tenant_id(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    other_tenant_id = _seed_tenant(engine)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["tenant_id"] = other_tenant_id
        sess["tenant_email"] = "owner@example.com"

    response = client.get("/workbench")

    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess["tenant_id"] == tenant_id


def test_user_without_tenant_membership_fails_safely(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    user_id = _seed_user_without_tenant(engine)
    client = app.test_client()

    login = client.post(
        "/login",
        data={"email": "orphan@example.com", "password": "safe-password-123"},
    )
    assert login.status_code == 200

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["tenant_email"] = "orphan@example.com"
    workbench = client.get("/workbench")
    assert workbench.status_code in {302, 303}
    assert workbench.headers["Location"].endswith("/login")


def test_workbench_without_product_profile_does_not_500(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = tenant_id
        sess["user_id"] = user_id
        sess["tenant_email"] = "owner@example.com"

    response = client.get("/workbench")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "训练你的 AI 外贸员" in html


def test_workbench_without_tenant_ai_quota_does_not_500(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["tenant_id"] = tenant_id
        sess["user_id"] = user_id
        sess["tenant_email"] = "owner@example.com"

    response = client.get("/workbench")

    assert response.status_code == 200


def test_settings_and_collection_recover_missing_tenant_context(monkeypatch) -> None:
    app, engine = _app(monkeypatch)
    tenant_id, user_id = _seed_user_with_tenant(engine)
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["tenant_email"] = "owner@example.com"

    settings = client.get("/settings/product-profile")
    collection = client.get("/collection")

    assert settings.status_code == 200
    assert collection.status_code == 200
    with client.session_transaction() as sess:
        assert sess["tenant_id"] == tenant_id
