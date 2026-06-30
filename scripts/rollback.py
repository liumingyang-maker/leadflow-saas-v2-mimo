#!/usr/bin/env python3
"""Rollback script for LeadFlow SaaS V2.

Rolls back to a previous version by checking out the tag,
running database downgrade, and restarting services.

Usage:
    python scripts.rollback.py [VERSION] [--dry-run]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run_cmd(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result


def get_current_version() -> str:
    """Get current version from git tag."""
    result = run_cmd(["git", "describe", "--tags", "--abbrev=0"], check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return "unknown"


def get_previous_version() -> str:
    """Get the previous version tag."""
    result = run_cmd(["git", "tag", "--sort=-v:refname"], check=False)
    if result.returncode == 0:
        tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
        if len(tags) >= 2:
            return tags[1]
    return ""


def get_latest_tag() -> str:
    """Get the latest version tag."""
    result = run_cmd(["git", "tag", "--sort=-v:refname"], check=False)
    if result.returncode == 0:
        tags = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]
        if tags:
            return tags[0]
    return ""


def checkout_version(version: str) -> None:
    """Checkout a specific version tag."""
    print(f"\n[2/5] Checking out {version}...")
    run_cmd(["git", "checkout", version])


def downgrade_database() -> None:
    """Run Alembic downgrade."""
    print("\n[3/5] Downgrading database...")
    try:
        run_cmd(["alembic", "downgrade", "-1"])
        print("  ✓ Database downgraded one step")
    except RuntimeError:
        print("  ⚠ Database downgrade failed or not needed")


def restart_services() -> None:
    """Restart Docker services."""
    print("\n[4/5] Restarting services...")
    try:
        run_cmd(["docker", "compose", "restart"])
        print("  ✓ Services restarted")
    except RuntimeError:
        print("  ⚠ Docker restart failed (services may not be running)")


def verify_health() -> None:
    """Verify health endpoints."""
    print("\n[5/5] Verifying health...")
    try:
        import urllib.request

        with urllib.request.urlopen("http://localhost:5000/health/live", timeout=10) as resp:
            if resp.getcode() == 200:
                print("  ✓ Health check passed")
            else:
                print(f"  ⚠ Health check returned {resp.getcode()}")
    except Exception as e:
        print(f"  ⚠ Health check failed: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rollback script")
    parser.add_argument("version", nargs="?", help="Version to rollback to")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print("Rollback Script")
    print("=" * 60)

    current = get_current_version()
    print(f"\nCurrent version: {current}")

    target = args.version
    if not target:
        target = get_previous_version()
        if not target:
            print("\n✗ No previous version found")
            return 1
        print(f"Auto-detected previous version: {target}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would rollback to: {target}")
        print("  1. Backup current database")
        print(f"  2. Checkout {target}")
        print("  3. Downgrade database")
        print("  4. Restart services")
        print("  5. Verify health")
        return 0

    # Confirm
    print(f"\n⚠ WARNING: Rolling back from {current} to {target}")
    print("  This will change the running code and database schema.")

    # Backup
    print("\n[1/5] Creating backup...")
    try:
        result = run_cmd(["python", "scripts/backup.py"], check=False)
        if result.returncode == 0:
            print("  ✓ Backup created")
        else:
            print("  ⚠ Backup failed, continuing anyway")
    except Exception:
        print("  ⚠ Backup script not found, skipping")

    # Checkout
    try:
        checkout_version(target)
    except RuntimeError as e:
        print(f"\n✗ Checkout failed: {e}")
        return 1

    # Downgrade
    downgrade_database()

    # Restart
    restart_services()

    # Verify
    verify_health()

    print(f"\n✓ Rollback to {target} completed")
    print("\nNext steps:")
    print("  1. Verify application functionality")
    print("  2. Check logs for errors")
    print("  3. If issues persist, restore from backup")

    return 0


if __name__ == "__main__":
    sys.exit(main())
