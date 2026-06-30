"""Tests for release and rollback scripts."""

from __future__ import annotations

import os


class TestReleaseScript:
    """Release script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/release.py")

    def test_script_has_dry_run(self) -> None:
        with open("scripts/release.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_has_skip_tests(self) -> None:
        with open("scripts/release.py") as f:
            content = f.read()
        assert "--skip-tests" in content

    def test_script_verifies_gates(self) -> None:
        with open("scripts/release.py") as f:
            content = f.read()
        assert "ruff" in content.lower()
        assert "pytest" in content.lower()

    def test_script_creates_tag(self) -> None:
        with open("scripts/release.py") as f:
            content = f.read()
        assert "git" in content and "tag" in content

    def test_script_generates_notes(self) -> None:
        with open("scripts/release.py") as f:
            content = f.read()
        assert "release_notes" in content or "RELEASE_NOTES" in content


class TestRollbackScript:
    """Rollback script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/rollback.py")

    def test_script_has_dry_run(self) -> None:
        with open("scripts/rollback.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_handles_backup(self) -> None:
        with open("scripts/rollback.py") as f:
            content = f.read()
        assert "backup" in content.lower()

    def test_script_handles_database(self) -> None:
        with open("scripts/rollback.py") as f:
            content = f.read()
        assert "downgrade" in content or "alembic" in content.lower()

    def test_script_handles_services(self) -> None:
        with open("scripts/rollback.py") as f:
            content = f.read()
        assert "restart" in content or "docker" in content.lower()

    def test_script_verifies_health(self) -> None:
        with open("scripts/rollback.py") as f:
            content = f.read()
        assert "health" in content.lower()
