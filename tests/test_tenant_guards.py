from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session


def _client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app.test_client(), engine


def _login(client, engine) -> str:
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme Export",
        },
    )
    from app.modules.accounts.models import EmailToken, Tenant

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
        tenant_id = session.scalars(select(Tenant.id)).one()
    client.get(f"/verify-email/{token}")
    response = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )
    assert response.status_code in {302, 303}
    return tenant_id


def _set_tenant(engine, tenant_id: str, **fields) -> None:
    from app.modules.accounts.models import Tenant

    with Session(engine) as session:
        tenant = session.get(Tenant, tenant_id)
        assert tenant is not None
        for key, value in fields.items():
            setattr(tenant, key, value)
        session.commit()


def test_workbench_requires_login(monkeypatch) -> None:
    client, _engine = _client(monkeypatch)

    response = client.get("/workbench")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")


def test_suspended_tenant_is_logged_out(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    tenant_id = _login(client, engine)
    _set_tenant(engine, tenant_id, status="suspended")

    response = client.get("/workbench")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as sess:
        assert "tenant_id" not in sess


def test_expired_trial_redirects_to_upgrade_without_loop(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    tenant_id = _login(client, engine)
    _set_tenant(
        engine,
        tenant_id,
        status="trial",
        trial_ends_at=datetime.now(UTC) - timedelta(days=1),
    )

    blocked = client.get("/workbench")
    allowed = client.get("/upgrade")

    assert blocked.status_code in {302, 303}
    assert blocked.headers["Location"].endswith("/upgrade")
    assert allowed.status_code == 200


def test_expired_paid_plan_redirects_to_upgrade(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    tenant_id = _login(client, engine)
    _set_tenant(
        engine,
        tenant_id,
        status="active",
        plan="pro",
        plan_expires_at=datetime.now(UTC) - timedelta(days=1),
    )

    response = client.get("/workbench")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/upgrade")
