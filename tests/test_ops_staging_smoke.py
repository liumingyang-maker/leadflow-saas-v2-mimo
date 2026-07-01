from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKUP_RESTORE = ROOT / "scripts" / "staging_backup_restore_smoke.py"
MIGRATION_ROLLBACK = ROOT / "scripts" / "staging_migration_rollback_smoke.py"
RUNBOOK = ROOT / "docs" / "RUNBOOK_STAGING.md"
CHECKLIST = ROOT / "docs" / "PRODUCTION_READINESS_CHECKLIST.md"
EVIDENCE_TEMPLATE = (
    ROOT / ".autopilot" / "evidence" / "templates" / "production-readiness-evidence-template.md"
)


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


def test_production_readiness_evidence_template_exists() -> None:
    assert EVIDENCE_TEMPLATE.is_file()


def test_production_readiness_evidence_template_has_required_sections() -> None:
    content = _read(EVIDENCE_TEMPLATE)
    content_lower = content.lower()

    required = [
        "release candidate name / version",
        "commit hash",
        "branch",
        "reviewer",
        "date",
        "environment",
        "Python version",
        "Docker version",
        "Ruff result",
        "Format check result",
        "Pytest result",
        "Browser / Playwright result",
        "Docker build result",
        "Staging compose smoke result",
        "Migration result",
        "Backup / restore smoke result",
        "Migration rollback smoke result",
        "`/health/live` result",
        "`/health/ready` result",
        "Real SMTP verification",
        "Real provider verification, if applicable",
        "Known limitations",
        "Unresolved risks",
        "Go / No-Go decision",
        "Approver",
    ]
    for section in required:
        assert section.lower() in content_lower


def test_production_readiness_evidence_template_uses_honest_placeholders() -> None:
    content = _read(EVIDENCE_TEMPLATE)

    for value in ("NOT_RUN", "BLOCKED", "PASS", "FAIL", "NEEDS_MANUAL_VERIFICATION"):
        assert value in content
    assert "This is a template, not final release evidence" in content
    assert "Do not mark a result `PASS`" in content


def test_production_readiness_checklist_references_required_rehearsals() -> None:
    content = _read(CHECKLIST)

    assert "scripts/staging_backup_restore_smoke.py" in content
    assert "scripts/staging_migration_rollback_smoke.py" in content
    assert "staging compose smoke passed" in content.lower()
    assert "/health/live" in content
    assert "/health/ready" in content


def test_production_readiness_checklist_is_not_ready_by_default() -> None:
    content = _read(CHECKLIST)

    assert "not production launch" in content
    assert "must not be treated as PASS" in content
    assert "- [x]" not in content.lower()


def test_staging_runbook_references_release_evidence_template() -> None:
    content = _read(RUNBOOK)

    assert "production-readiness-evidence-template.md" in content
    assert "NOT_RUN" in content
    assert "NEEDS_MANUAL_VERIFICATION" in content
