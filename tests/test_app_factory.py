from __future__ import annotations

import importlib

import pytest


def test_create_app_testing_config_exposes_live_health_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app

    flask_app = create_app("testing")

    assert flask_app.config["TESTING"] is True
    assert flask_app.config["WTF_CSRF_ENABLED"] is False
    assert flask_app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert flask_app.config["SESSION_COOKIE_SAMESITE"] == "Lax"

    response = flask_app.test_client().get("/health/live")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}


def test_resolve_config_uses_app_env_when_name_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app.config import TestingConfig, resolve_config

    assert resolve_config(None) is TestingConfig


def test_production_config_requires_strong_secret_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    from app.config import resolve_config

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        resolve_config("production")

    monkeypatch.setenv("SECRET_KEY", "dev")
    with pytest.raises(RuntimeError, match="weak"):
        resolve_config("production")

    monkeypatch.setenv("SECRET_KEY", "a-32-char-production-key-that-is-ok!")
    monkeypatch.delenv("TENANT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY"):
        resolve_config("production")

    monkeypatch.setenv("TENANT_SECRET_KEY", "short")
    with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY.*weak"):
        resolve_config("production")

    monkeypatch.setenv("TENANT_SECRET_KEY", "a-32-char-tenant-secret-key-ok!!!")
    assert resolve_config("production").SESSION_COOKIE_SECURE is True


def test_create_app_import_has_no_thread_timer_or_network_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import threading

    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("import/create_app must not start background or network work")

    monkeypatch.setattr(threading.Thread, "start", fail)
    monkeypatch.setattr(threading.Timer, "start", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    app_module = importlib.import_module("app")
    flask_app = app_module.create_app("testing")

    assert flask_app.name == "app"
