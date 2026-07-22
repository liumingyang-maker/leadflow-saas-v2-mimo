from __future__ import annotations

from flask import request
from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.middleware.proxy_fix import ProxyFix

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(monkeypatch):
    """Testing-mode client (CSRF disabled)."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("testing")
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app.test_client(), engine


def _dev_client(monkeypatch):
    """Development-mode client (CSRF enabled)."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.extensions import Base, get_engine, reset_engine_for_tests

    reset_engine_for_tests()
    flask_app = create_app("development")
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    reset_engine_for_tests()
    engine = get_engine(flask_app)
    Base.metadata.create_all(engine)
    return flask_app.test_client(), engine, flask_app


def _get_csrf(client) -> str:
    """Extract the CSRF token value from the login page."""
    from re import search

    html = client.get("/login").get_data(as_text=True)
    m = search(r'csrf_token" value="([^"]+)"', html)
    assert m is not None, "csrf_token input not found in /login"
    return m.group(1)


def _set_basic_session(client, data: dict) -> None:
    with client.session_transaction() as sess:
        sess.update(data)


# ---------------------------------------------------------------------------
# CSRF presence (dev mode)
# ---------------------------------------------------------------------------


def test_csrf_token_rendered_on_login_page(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    html = app.test_client().get("/login").get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'value="' in html


def test_csrf_token_rendered_on_register_page(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    html = app.test_client().get("/register").get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'value="' in html


def test_csrf_token_rendered_on_forgot_password_page(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    html = app.test_client().get("/forgot-password").get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'value="' in html


def test_csrf_token_rendered_on_admin_login_page(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    html = app.test_client().get("/admin/login").get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'value="' in html


# ---------------------------------------------------------------------------
# CSRF enforcement (dev mode)
# ---------------------------------------------------------------------------


def test_post_without_csrf_token_is_rejected(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    response = app.test_client().post(
        "/login",
        data={"email": "owner@example.com", "password": "safe-password-123"},
    )
    assert response.status_code == 400


def test_post_with_correct_csrf_token_succeeds(monkeypatch) -> None:
    client, _engine, app = _dev_client(monkeypatch)
    csrf_token = _get_csrf(client)

    reg_resp = client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
            "csrf_token": csrf_token,
        },
    )
    assert reg_resp.status_code in {302, 303}


def test_wrong_csrf_token_is_rejected(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    response = app.test_client().post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
            "csrf_token": "this-is-a-bad-token",
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Cookie attributes
# ---------------------------------------------------------------------------


def test_session_cookie_httponly_samesite_secure(monkeypatch) -> None:
    """Login sets HttpOnly, SameSite=Lax; Secure only in production."""
    client, engine = _client(monkeypatch)

    # Register + verify + login
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
        },
    )
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
    client.get(f"/verify-email/{token}")
    resp = client.post(
        "/login", data={"email": "owner@example.com", "password": "safe-password-123"}
    )

    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie
    assert "Secure" not in set_cookie


def test_session_cookie_secure_in_production(monkeypatch) -> None:
    """Production config forces Secure flag."""
    monkeypatch.setenv("SECRET_KEY", "a-32-char-production-key-that-is-ok!")
    monkeypatch.setenv("TENANT_SECRET_KEY", "a-32-char-tenant-secret-key-ok!!!")
    monkeypatch.setenv("TRACKING_SIGNING_KEY", "a-32-char-tracking-signing-key-ok!")
    monkeypatch.setenv("UNSUBSCRIBE_SIGNING_KEY", "a-32-char-unsubscribe-signing-key!")
    monkeypatch.setenv("INBOUND_TOKEN_KEY", "a-32-char-inbound-token-key-ok!!!!")
    from app.config import resolve_config

    config = resolve_config("production")
    assert config.SESSION_COOKIE_SECURE is True


# ---------------------------------------------------------------------------
# Session rotation / fixation protection
# ---------------------------------------------------------------------------


def test_login_clears_old_session(monkeypatch) -> None:
    client, engine = _client(monkeypatch)
    # Set stale session data
    with client.session_transaction() as sess:
        sess["tenant_id"] = "old-tenant"
        sess["is_admin"] = True
        sess["old_stale"] = "should-be-gone"

    # Register + verify + login
    client.post(
        "/register",
        data={
            "email": "owner@example.com",
            "password": "safe-password-123",
            "company_name": "Acme",
        },
    )
    from app.modules.accounts.models import EmailToken

    with Session(engine) as session:
        token = session.scalars(
            select(EmailToken.token).where(EmailToken.token_type == "verify")
        ).one()
    client.get(f"/verify-email/{token}")
    client.post("/login", data={"email": "owner@example.com", "password": "safe-password-123"})

    with client.session_transaction() as sess:
        assert sess.get("tenant_id") is not None
        assert "is_admin" not in sess
        assert "old_stale" not in sess


def test_admin_login_clears_tenant_session(monkeypatch) -> None:
    client, _, app = _dev_client(monkeypatch)
    from app.modules.accounts.admin_service import create_admin

    create_admin(
        app,
        email="admin@example.com",
        password="temporary-safe-password-123",
        must_change_password=False,
    )

    # Set a tenant session first
    with client.session_transaction() as sess:
        sess["tenant_id"] = "tenant"
        sess["tenant_email"] = "user@example.com"

    # Admin login must clear it
    csrf_token = _get_csrf(client)
    response = client.post(
        "/admin/login",
        data={
            "email": "admin@example.com",
            "password": "temporary-safe-password-123",
            "csrf_token": csrf_token,
        },
    )
    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert sess.get("is_admin") is True
        assert "tenant_id" not in sess


def test_logout_clears_session(monkeypatch) -> None:
    client, _engine = _client(monkeypatch)
    with client.session_transaction() as sess:
        sess["tenant_id"] = "tenant"
        sess["user_id"] = "user"

    response = client.post("/logout")
    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert "tenant_id" not in sess
        assert "user_id" not in sess


def test_admin_logout_clears_session(monkeypatch) -> None:
    client, _engine = _client(monkeypatch)
    with client.session_transaction() as sess:
        sess["is_admin"] = True
        sess["admin_id"] = "admin-1"

    response = client.post("/admin/logout")
    assert response.status_code in {302, 303}
    with client.session_transaction() as sess:
        assert "is_admin" not in sess
        assert "admin_id" not in sess


# ---------------------------------------------------------------------------
# ProxyFix behaviour
# ---------------------------------------------------------------------------


def test_proxy_fix_disabled_by_default(monkeypatch) -> None:
    """Without PROXY_FIX_HOPS, X-Forwarded-For is not trusted."""
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app

    app = create_app("testing")
    assert not isinstance(app.wsgi_app, ProxyFix)

    @app.get("/whoami")
    def whoami():
        return request.remote_addr or "unknown"

    client = app.test_client()
    resp = client.get("/whoami", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.get_data(as_text=True) != "1.2.3.4"


def test_proxy_fix_one_hop_trusts_first_x_forwarded_for(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app

    app = create_app("testing")
    app.config["PROXY_FIX_HOPS"] = 1

    from app.core.proxy import register_proxy_middleware

    register_proxy_middleware(app)
    assert isinstance(app.wsgi_app, ProxyFix)

    # Manually test that ProxyFix modifies the WSGI environ

    def simple_app(environ, start_response):
        status = "200 OK"
        headers = [("Content-Type", "text/plain")]
        start_response(status, headers)
        return [environ.get("REMOTE_ADDR", "unknown").encode()]

    wrapped = ProxyFix(simple_app, x_for=1, x_proto=1, x_host=1)
    environ = {
        "REQUEST_METHOD": "GET",
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "80",
        "REMOTE_ADDR": "10.0.0.1",  # proxy address
        "HTTP_X_FORWARDED_FOR": "1.2.3.4",  # real client IP
    }
    result = b"".join(wrapped(environ, lambda *a: None))
    assert result == b"1.2.3.4"


def test_proxy_fix_hops_are_validated(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")
    from app import create_app
    from app.core.proxy import register_proxy_middleware

    app = create_app("testing")
    app.config["PROXY_FIX_HOPS"] = -1
    try:
        register_proxy_middleware(app)
    except RuntimeError as exc:
        assert "PROXY_FIX_HOPS" in str(exc)
    else:
        raise AssertionError("negative proxy hops must be rejected")


# ---------------------------------------------------------------------------
# JSON error stability
# ---------------------------------------------------------------------------


def test_json_request_with_missing_csrf_returns_stable_error(monkeypatch) -> None:
    _client_obj, _engine, app = _dev_client(monkeypatch)
    response = app.test_client().post(
        "/login",
        data='{"email":"test@example.com"}',
        content_type="application/json",
    )
    assert response.status_code == 400
    body = response.get_json()
    assert body is not None
    assert body.get("ok") is False
    assert body.get("error") == "bad_request"
