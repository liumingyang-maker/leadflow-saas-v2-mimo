from __future__ import annotations

import re

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


def test_ready_health_checks_database(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/ready")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "checks": {"database": "ok"}}


def test_favicon_request_is_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/favicon.ico")

    assert response.status_code == 204
