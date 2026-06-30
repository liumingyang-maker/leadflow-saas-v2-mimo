#!/usr/bin/env python3
"""Database backup script.

Supports SQLite (file copy) and PostgreSQL (pg_dump).

Usage:
    python scripts/backup.py [--output-dir DIR] [--dry-run]
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


def backup_sqlite(db_path: str, output_dir: str) -> str:
    """Backup SQLite database by file copy."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"leadflow-v2-{timestamp}.db"
    backup_path = os.path.join(output_dir, backup_name)

    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Database file not found: {db_path}")

    shutil.copy2(db_path, backup_path)

    # Verify backup
    if os.path.getsize(backup_path) == 0:
        os.remove(backup_path)
        raise RuntimeError("Backup file is empty")

    return backup_path


def backup_postgres(output_dir: str) -> str:
    """Backup PostgreSQL database using pg_dump."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"leadflow-v2-{timestamp}.sql"
    backup_path = os.path.join(output_dir, backup_name)

    database_url = get_database_url()
    result = subprocess.run(
        ["pg_dump", database_url, "-f", backup_path],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr}")

    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Database backup")
    parser.add_argument("--output-dir", default="backups", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print("Database Backup")
    print("=" * 60)

    database_url = get_database_url()
    print(f"\nDatabase: {database_url.split('@')[-1] if '@' in database_url else database_url}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would backup to: {args.output_dir}/")
        if database_url.startswith("sqlite:///"):
            print("  Method: SQLite file copy")
        else:
            print("  Method: pg_dump")
        return 0

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    # Perform backup
    print(f"\nBacking up to: {args.output_dir}/")
    try:
        if database_url.startswith("sqlite:///"):
            db_file = database_url.replace("sqlite:///", "")
            backup_path = backup_sqlite(db_file, args.output_dir)
        else:
            backup_path = backup_postgres(args.output_dir)

        size = os.path.getsize(backup_path)
        print(f"\n✓ Backup completed: {backup_path}")
        print(f"  Size: {size:,} bytes")

    except Exception as e:
        print(f"\n✗ Backup failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
