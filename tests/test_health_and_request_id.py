from __future__ import annotations

import re
from typing import NoReturn

import pytest

REQUEST_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app

    return create_app("testing")


def test_every_response_gets_request_id_header(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/live")

    request_id = response.headers["X-Request-ID"]
    assert REQUEST_ID_PATTERN.match(request_id)
    assert response.get_json() == {"ok": True}


def test_inbound_request_id_is_reused_when_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)
    supplied = "a" * 32

    response = flask_app.test_client().get("/health/live", headers={"X-Request-ID": supplied})

    assert response.headers["X-Request-ID"] == supplied


def test_invalid_inbound_request_id_is_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get(
        "/health/live",
        headers={"X-Request-ID": "not valid / C:/private/admin.db"},
    )

    assert response.headers["X-Request-ID"] != "not valid / C:/private/admin.db"
    assert REQUEST_ID_PATTERN.match(response.headers["X-Request-ID"])


class _PassingRedis:
    def ping(self) -> bool:
        return True


def _failing_redis(*_args: object, **_kwargs: object) -> NoReturn:
    raise RuntimeError("redis unavailable")


def test_ready_health_checks_database(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "checks": {"database": "ok", "redis": "skipped"},
    }


def test_ready_health_checks_database_and_redis_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    flask_app = _app(monkeypatch)
    flask_app.config["REDIS_URL"] = "redis://redis:6379/0"

    from app.core import health

    monkeypatch.setattr(health.Redis, "from_url", lambda *_args, **_kwargs: _PassingRedis())

    response = flask_app.test_client().get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_ready_health_fails_when_redis_is_unavailable_in_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["REDIS_URL"] = "redis://localhost:16379/0"

    from app.core import health

    monkeypatch.setattr(health.Redis, "from_url", _failing_redis)

    response = flask_app.test_client().get("/health/ready")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["redis"] == "error: RuntimeError"


def test_favicon_request_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/favicon.ico")

    assert response.status_code == 204
