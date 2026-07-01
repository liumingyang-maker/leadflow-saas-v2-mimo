from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.security import check_password_hash


def _client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app.test_client(), engine, flask_app


def test_empty_database_has_no_default_admin(monkeypatch) -> None:
    _client_obj, engine, _app = _client(monkeypatch)

    from app.modules.accounts.models import AdminUser

    with Session(engine) as session:
        assert session.scalar(select(AdminUser)) is None


def test_create_admin_hashes_password_and_rejects_weak_or_duplicate(monkeypatch) -> None:
    _client_obj, engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import AdminAccountError, create_admin
    from app.modules.accounts.models import AdminUser

    with pytest.raises(AdminAccountError):
        create_admin(app, email="owner@example.com", password="short")

    admin = create_admin(app, email="Owner@Example.com ", password="temporary-safe-password-123")
    with pytest.raises(AdminAccountError):
        create_admin(app, email="owner@example.com", password="another-safe-password-456")

    with Session(engine) as session:
        stored = session.scalars(select(AdminUser)).one()
        assert stored.id == admin.id
        assert stored.email == "owner@example.com"
        assert stored.password_hash != "temporary-safe-password-123"
        assert check_password_hash(stored.password_hash, "temporary-safe-password-123")
        assert stored.must_change_password is True


def test_admin_login_uses_separate_session_boundary(monkeypatch) -> None:
    client, _engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin

    create_admin(
        app,
        email="admin@example.com",
        password="temporary-safe-password-123",
        must_change_password=False,
    )
    with client.session_transaction() as sess:
        sess["tenant_id"] = "tenant"
        sess["tenant_email"] = "owner@example.com"

    response = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/admin")
    with client.session_transaction() as sess:
        assert sess["is_admin"] is True
        assert sess["admin_email"] == "admin@example.com"
        assert "tenant_id" not in sess
        assert "tenant_email" not in sess


def test_admin_login_rate_limits_failed_attempts(monkeypatch) -> None:
    client, _engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin

    create_admin(
        app,
        email="admin@example.com",
        password="temporary-safe-password-123",
        must_change_password=False,
    )

    for _ in range(5):
        response = client.post(
            "/admin/login",
            data={"email": "admin@example.com", "password": "wrong-password"},
        )
        assert response.status_code == 200

    limited = client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    assert limited.status_code == 429


def test_admin_console_requires_admin_session(monkeypatch) -> None:
    client, _engine, _app = _client(monkeypatch)

    response = client.get("/admin")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/admin/login")


def test_admin_must_change_password_redirects_from_dashboard(monkeypatch) -> None:
    client, _engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin

    create_admin(app, email="admin@example.com", password="temporary-safe-password-123")
    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    response = client.get("/admin")

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/admin/change-password")


def test_admin_must_change_password_can_access_change_password(monkeypatch) -> None:
    client, _engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin

    create_admin(app, email="admin@example.com", password="temporary-safe-password-123")
    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    response = client.get("/admin/change-password")

    assert response.status_code == 200
    assert "Change password" in response.get_data(as_text=True)


def test_admin_must_change_password_can_logout(monkeypatch) -> None:
    client, _engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin

    create_admin(app, email="admin@example.com", password="temporary-safe-password-123")
    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    response = client.post("/admin/logout")

    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert "is_admin" not in sess


def test_admin_password_change_clears_must_change_password(monkeypatch) -> None:
    client, engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin
    from app.modules.accounts.models import AdminUser

    create_admin(app, email="admin@example.com", password="temporary-safe-password-123")
    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )

    response = client.post(
        "/admin/change-password",
        data={"password": "new-temporary-safe-password-456"},
    )

    assert response.status_code in {302, 303}
    assert response.headers["Location"].endswith("/admin")
    with client.session_transaction() as sess:
        assert sess["admin_must_change_password"] is False
    with Session(engine) as session:
        admin = session.scalars(select(AdminUser)).one()
        assert admin.must_change_password is False
        assert check_password_hash(admin.password_hash, "new-temporary-safe-password-456")


def test_admin_console_escapes_tenant_fields(monkeypatch) -> None:
    client, engine, app = _client(monkeypatch)

    from app.modules.accounts.admin_service import create_admin
    from app.modules.accounts.models import Tenant

    create_admin(
        app,
        email="admin@example.com",
        password="temporary-safe-password-123",
        must_change_password=False,
    )
    with Session(engine) as session:
        session.add(
            Tenant(
                company_name='<img src=x onerror="alert(1)">',
                industry="<script>alert(2)</script>",
            )
        )
        session.commit()

    client.post(
        "/admin/login",
        data={"email": "admin@example.com", "password": "temporary-safe-password-123"},
    )
    response = client.get("/admin")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert '<img src=x onerror="alert(1)">' not in html
    assert "<script>alert(2)</script>" not in html
    assert "&lt;img" in html
    assert "&lt;script&gt;" in html
