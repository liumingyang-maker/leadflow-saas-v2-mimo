"""Tests for staging smoke test script."""

from __future__ import annotations

import os


class TestStagingSmokeScript:
    """Staging smoke test script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/staging_smoke.py")

    def test_script_has_dry_run(self) -> None:
        with open("scripts/staging_smoke.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_has_base_url_option(self) -> None:
        with open("scripts/staging_smoke.py") as f:
            content = f.read()
        assert "--base-url" in content

    def test_script_checks_health_endpoints(self) -> None:
        with open("scripts/staging_smoke.py") as f:
            content = f.read()
        assert "/health/live" in content
        assert "/health/ready" in content

    def test_script_checks_security_headers(self) -> None:
        with open("scripts/staging_smoke.py") as f:
            content = f.read()
        assert "X-Content-Type-Options" in content
        assert "Content-Security-Policy" in content

    def test_script_checks_login_page(self) -> None:
        with open("scripts/staging_smoke.py") as f:
            content = f.read()
        assert "/login" in content


class TestStagingComposeExists:
    """Staging compose file must exist."""

    def test_staging_compose_exists(self) -> None:
        assert os.path.isfile("docker-compose.staging.yml")

    def test_staging_compose_uses_postgres(self) -> None:
        with open("docker-compose.staging.yml") as f:
            content = f.read()
        assert "postgres" in content.lower()
