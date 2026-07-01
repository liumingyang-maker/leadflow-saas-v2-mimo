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


def test_hsts_is_added_for_production_like_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["SESSION_COOKIE_SECURE"] = True
    flask_app.config["ALLOWED_HOSTS"] = "app.example.com"

    response = flask_app.test_client().get("/health/live", headers={"Host": "app.example.com"})

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_hsts_is_not_forced_in_testing(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/live")

    assert "Strict-Transport-Security" not in response.headers


def test_invalid_host_is_rejected_for_production_like_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["SESSION_COOKIE_SECURE"] = True
    flask_app.config["ALLOWED_HOSTS"] = "app.example.com,localhost"

    response = flask_app.test_client().get("/health/live", headers={"Host": "evil.example"})

    assert response.status_code == 400


def test_valid_host_is_accepted_for_production_like_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    flask_app = _app(monkeypatch)
    flask_app.config["TESTING"] = False
    flask_app.config["DEBUG"] = False
    flask_app.config["SESSION_COOKIE_SECURE"] = True
    flask_app.config["ALLOWED_HOSTS"] = "app.example.com,localhost"

    response = flask_app.test_client().get("/health/live", headers={"Host": "app.example.com"})

    assert response.status_code == 200


def test_host_allowlist_is_not_forced_in_testing(monkeypatch: pytest.MonkeyPatch) -> None:
    flask_app = _app(monkeypatch)

    response = flask_app.test_client().get("/health/live", headers={"Host": "evil.example"})

    assert response.status_code == 200


def test_rate_limit_keys_hash_user_controlled_identifiers() -> None:
    from app.core.abuse import rate_limit_key_for_tests

    key = rate_limit_key_for_tests("auth:login", ["1.2.3.4", "Owner@Example.com"])

    assert "owner@example.com" not in key
    assert "1.2.3.4" not in key
    assert key.startswith("leadflow:rate-limit:auth:login:")


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
