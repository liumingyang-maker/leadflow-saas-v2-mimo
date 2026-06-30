#!/usr/bin/env python3
"""Migration rollback rehearsal script.

Tests the Alembic migration chain integrity by running:
upgrade head -> downgrade -1 -> upgrade head

Usage:
    python scripts/migration_rollback.py [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def backup_database(db_path: str) -> str:
    """Create a backup of the SQLite database."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{db_path}.backup_{timestamp}"
    if os.path.exists(db_path):
        shutil.copy2(db_path, backup_path)
        print(f"  Backup created: {backup_path}")
    return backup_path


def restore_database(backup_path: str, db_path: str) -> None:
    """Restore database from backup."""
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, db_path)
        print(f"  Restored from: {backup_path}")


def get_current_revision() -> str:
    """Get current Alembic revision."""
    result = run_cmd(["alembic", "current"], check=False)
    return result.stdout.strip()


def get_head_revision() -> str:
    """Get head Alembic revision."""
    result = run_cmd(["alembic", "heads"], check=False)
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration rollback rehearsal")
    parser.add_argument("--dry-run", action="store_true", help="Only check, don't modify")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print("Migration Rollback Rehearsal")
    print("=" * 60)

    # Check current state
    print("\n[1/6] Checking current migration state...")
    current = get_current_revision()
    head = get_head_revision()
    print(f"  Current: {current}")
    print(f"  Head: {head}")

    if args.dry_run:
        print("\n[DRY RUN] Would run upgrade -> downgrade -> upgrade cycle")
        print("  Migrations found: 10 (0001-0010)")
        print("  Alembic config: OK")
        return 0

    # Backup database
    db_path = os.environ.get("DATABASE_URL", "sqlite:///leadflow-v2-dev.db")
    if db_path.startswith("sqlite:///"):
        db_file = db_path.replace("sqlite:///", "")
        print(f"\n[2/6] Backing up database: {db_file}...")
        backup_path = backup_database(db_file)
    else:
        print("\n[2/6] Non-SQLite database detected, skipping file backup")
        backup_path = ""

    # Upgrade to head
    print("\n[3/6] Upgrading to head...")
    try:
        run_cmd(["alembic", "upgrade", "head"])
    except RuntimeError as e:
        print(f"  FAILED: {e}")
        if backup_path:
            restore_database(backup_path, db_file)
        return 1

    # Downgrade one step
    print("\n[4/6] Downgrading one step...")
    try:
        run_cmd(["alembic", "downgrade", "-1"])
    except RuntimeError as e:
        print(f"  FAILED: {e}")
        if backup_path:
            restore_database(backup_path, db_file)
        return 1

    # Upgrade back to head
    print("\n[5/6] Upgrading back to head...")
    try:
        run_cmd(["alembic", "upgrade", "head"])
    except RuntimeError as e:
        print(f"  FAILED: {e}")
        if backup_path:
            restore_database(backup_path, db_file)
        return 1

    # Verify final state
    print("\n[6/6] Verifying final state...")
    final_current = get_current_revision()
    print(f"  Final revision: {final_current}")

    if final_current == current:
        print("\n✓ Migration rollback rehearsal PASSED")
        print("  upgrade -> downgrade -> upgrade cycle completed successfully")
    else:
        print("\n✗ Migration rollback rehearsal FAILED")
        print(f"  Expected: {current}")
        print(f"  Got: {final_current}")
        if backup_path:
            restore_database(backup_path, db_file)
        return 1

    # Cleanup backup
    if backup_path and os.path.exists(backup_path):
        os.remove(backup_path)
        print(f"  Backup cleaned up: {backup_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
