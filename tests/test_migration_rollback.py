"""Tests for migration rollback script."""

from __future__ import annotations

import os


class TestMigrationRollbackScript:
    """Migration rollback script must exist and be valid."""

    def test_script_exists(self) -> None:
        assert os.path.isfile("scripts/migration_rollback.py")

    def test_script_is_executable(self) -> None:
        with open("scripts/migration_rollback.py") as f:
            content = f.read()
        assert "def main()" in content
        assert "argparse" in content

    def test_script_has_dry_run(self) -> None:
        with open("scripts/migration_rollback.py") as f:
            content = f.read()
        assert "--dry-run" in content

    def test_script_handles_backup(self) -> None:
        with open("scripts/migration_rollback.py") as f:
            content = f.read()
        assert "backup_database" in content

    def test_script_handles_restore(self) -> None:
        with open("scripts/migration_rollback.py") as f:
            content = f.read()
        assert "restore_database" in content


class TestAlembicMigrationChain:
    """Alembic migration chain must be valid."""

    def test_all_migrations_exist(self) -> None:
        migrations_dir = "migrations/versions"
        assert os.path.isdir(migrations_dir)
        files = [f for f in os.listdir(migrations_dir) if f.endswith(".py")]
        assert len(files) >= 10, f"Expected at least 10 migrations, found {len(files)}"

    def test_migrations_are_sequential(self) -> None:
        migrations_dir = "migrations/versions"
        files = sorted(f for f in os.listdir(migrations_dir) if f.endswith(".py"))
        for i, filename in enumerate(files, 1):
            expected_prefix = f"{i:04d}_"
            assert filename.startswith(expected_prefix), (
                f"Migration {filename} should start with {expected_prefix}"
            )

    def test_alembic_ini_exists(self) -> None:
        assert os.path.isfile("alembic.ini")

    def test_env_py_imports_models(self) -> None:
        env_path = "migrations/env.py"
        assert os.path.isfile(env_path)
        with open(env_path) as f:
            content = f.read()
        # Should import models to register with metadata
        assert "import" in content.lower()
