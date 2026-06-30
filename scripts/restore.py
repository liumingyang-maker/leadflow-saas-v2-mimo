#!/usr/bin/env python3
"""Database restore script.

Supports SQLite (file replacement) and PostgreSQL (psql).

Usage:
    python scripts/restore.py BACKUP_FILE [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def get_database_url() -> str:
    """Get database URL from environment."""
    return os.environ.get("DATABASE_URL", "sqlite:///leadflow-v2-dev.db")


def restore_sqlite(backup_path: str, db_path: str) -> None:
    """Restore SQLite database from backup."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    # Create pre-restore backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    pre_restore_backup = f"{db_path}.pre_restore_{timestamp}"
    if os.path.exists(db_path):
        shutil.copy2(db_path, pre_restore_backup)
        print(f"  Pre-restore backup: {pre_restore_backup}")

    # Restore
    shutil.copy2(backup_path, db_path)
    print(f"  Restored from: {backup_path}")


def restore_postgres(backup_path: str) -> None:
    """Restore PostgreSQL database from backup."""
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found: {backup_path}")

    database_url = get_database_url()
    result = subprocess.run(
        ["psql", database_url, "-f", backup_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"psql failed: {result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Database restore")
    parser.add_argument("backup_file", help="Path to backup file")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print("Database Restore")
    print("=" * 60)

    if not os.path.exists(args.backup_file):
        print(f"\n✗ Backup file not found: {args.backup_file}")
        return 1

    backup_size = os.path.getsize(args.backup_file)
    print(f"\nBackup file: {args.backup_file}")
    print(f"Size: {backup_size:,} bytes")

    database_url = get_database_url()
    print(f"Target: {database_url.split('@')[-1] if '@' in database_url else database_url}")

    if args.dry_run:
        print("\n[DRY RUN] Would restore from backup")
        if database_url.startswith("sqlite:///"):
            print("  Method: SQLite file replacement")
        else:
            print("  Method: psql")
        return 0

    # Perform restore
    print("\nRestoring...")
    try:
        if database_url.startswith("sqlite:///"):
            db_file = database_url.replace("sqlite:///", "")
            restore_sqlite(args.backup_file, db_file)
        else:
            restore_postgres(args.backup_file)

        print("\n✓ Restore completed successfully")

    except Exception as e:
        print(f"\n✗ Restore failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
