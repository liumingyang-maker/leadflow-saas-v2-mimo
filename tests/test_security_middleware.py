from __future__ import annotations

import pytest


def _app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-that-is-long-enough")

    from app import create_app

    return create_app("testing")


def test_security_headers_are_added_to_success_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/live")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in response.headers["Permissions-Policy"]


def test_json_404_uses_stable_error_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/missing", headers={"Accept": "application/json"})

    assert response.status_code == 404
    assert response.get_json() == {"ok": False, "error": "not_found"}
    assert "Traceback" not in response.get_data(as_text=True)
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_unhandled_errors_are_sanitized_for_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)
    flask_app.config["PROPAGATE_EXCEPTIONS"] = False

    @flask_app.get("/explode")
    def explode():
        raise RuntimeError("C:/private/admin.db secret=sk-test-value")

    response = flask_app.test_client().get("/explode", headers={"Accept": "application/json"})
    body = response.get_data(as_text=True)

    assert response.status_code == 500
    assert response.get_json() == {"ok": False, "error": "internal_error"}
    assert "sk-test-value" not in body
    assert "admin.db" not in body
    assert "Traceback" not in body
    assert response.headers["X-Frame-Options"] == "DENY"
