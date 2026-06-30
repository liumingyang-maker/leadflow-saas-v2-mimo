"""Tests for security headers and CSP baseline."""

from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture()
def app():
    app = create_app("testing")
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


class TestSecurityHeaders:
    """All responses MUST include security headers."""

    def test_x_content_type_options(self, client) -> None:
        resp = client.get("/health/live")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client) -> None:
        resp = client.get("/health/live")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_referrer_policy(self, client) -> None:
        resp = client.get("/health/live")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_permissions_policy(self, client) -> None:
        resp = client.get("/health/live")
        policy = resp.headers.get("Permissions-Policy", "")
        assert "geolocation=()" in policy
        assert "microphone=()" in policy
        assert "camera=()" in policy

    def test_csp_baseline(self, client) -> None:
        """Responses MUST include a Content-Security-Policy header."""
        resp = client.get("/health/live")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp


class TestUploadLimits:
    """Upload size limits MUST be configured."""

    def test_max_content_length_configured(self, app) -> None:
        limit = app.config.get("MAX_CONTENT_LENGTH", 0)
        assert limit > 0, "MAX_CONTENT_LENGTH must be set"
        assert limit <= 50 * 1024 * 1024, "MAX_CONTENT_LENGTH should not exceed 50MB"
