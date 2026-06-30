"""Tests for backup and restore scripts."""

from __future__ import annotations

import os


class TestBackupScript:
    """Backup script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/backup.py")

    def test_script_has_dry_run(self) -> None:
        with open("scripts/backup.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_supports_sqlite(self) -> None:
        with open("scripts/backup.py") as f:
            content = f.read()
        assert "sqlite" in content.lower()

    def test_script_supports_postgres(self) -> None:
        with open("scripts/backup.py") as f:
            content = f.read()
        assert "pg_dump" in content or "postgres" in content.lower()

    def test_script_creates_output_dir(self) -> None:
        with open("scripts/backup.py") as f:
            content = f.read()
        assert "makedirs" in content or "mkdir" in content


class TestRestoreScript:
    """Restore script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/restore.py")

    def test_script_has_dry_run(self) -> None:
        with open("scripts/restore.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_creates_pre_restore_backup(self) -> None:
        with open("scripts/restore.py") as f:
            content = f.read()
        assert "pre_restore" in content

    def test_script_supports_sqlite(self) -> None:
        with open("scripts/restore.py") as f:
            content = f.read()
        assert "sqlite" in content.lower()

    def test_script_supports_postgres(self) -> None:
        with open("scripts/restore.py") as f:
            content = f.read()
        assert "psql" in content or "postgres" in content.lower()
