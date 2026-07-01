from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_RESTORE = ROOT / "scripts" / "staging_backup_restore_smoke.py"
MIGRATION_ROLLBACK = ROOT / "scripts" / "staging_migration_rollback_smoke.py"
RUNBOOK = ROOT / "docs" / "RUNBOOK_STAGING.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_staging_backup_restore_smoke_script_exists_and_is_executable() -> None:
    assert BACKUP_RESTORE.is_file()
    assert os.access(BACKUP_RESTORE, os.X_OK)


def test_staging_migration_rollback_smoke_script_exists_and_is_executable() -> None:
    assert MIGRATION_ROLLBACK.is_file()
    assert os.access(MIGRATION_ROLLBACK, os.X_OK)


def test_backup_restore_smoke_has_staging_safety_guards() -> None:
    content = _read(BACKUP_RESTORE)

    assert "STAGING BACKUP/RESTORE SMOKE CHECK" in content
    assert "APP_ENV=production" in content
    assert "--confirm-staging" in content
    assert "leadflow-backup-restore-smoke" in content
    assert "docker-compose.staging.yml" in content


def test_backup_restore_smoke_uses_postgres_native_restore_check_database() -> None:
    content = _read(BACKUP_RESTORE)

    assert "pg_dump" in content
    assert "pg_restore" in content
    assert "restore_check" in content
    for table in ("alembic_version", "tenants", "users", "jobs", "leads"):
        assert table in content


def test_migration_rollback_smoke_has_staging_safety_guards() -> None:
    content = _read(MIGRATION_ROLLBACK)

    assert "STAGING MIGRATION ROLLBACK SMOKE CHECK" in content
    assert "APP_ENV=production" in content
    assert "--confirm-staging" in content
    assert "leadflow-migration-rollback-smoke" in content
    assert "docker-compose.staging.yml" in content


def test_migration_rollback_smoke_runs_alembic_downgrade_and_upgrade() -> None:
    content = _read(MIGRATION_ROLLBACK)

    assert '"current"' in content
    assert '"downgrade", "-1"' in content
    assert '"upgrade", "head"' in content
    assert "may not support rollback" in content


def test_staging_runbook_references_ops_smoke_scripts() -> None:
    content = _read(RUNBOOK)

    assert "scripts/staging_backup_restore_smoke.py" in content
    assert "scripts/staging_migration_rollback_smoke.py" in content
    assert "backup restored into restore_check" in content
    assert "downgrade -1 and upgrade head" in content
