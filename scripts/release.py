#!/usr/bin/env python3
"""Release script for LeadFlow SaaS V2.

Creates a release branch, runs final verification, tags the release.

Usage:
    python scripts/release.py VERSION [--dry-run] [--skip-tests]
"""

from __future__ import annotations

import argparse
import os
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


def get_current_version() -> str:
    """Read current version from pyproject.toml or git tag."""
    result = run_cmd(["git", "describe", "--tags", "--abbrev=0"], check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return "v0.0.0"


def verify_gates() -> bool:
    """Run all quality gates."""
    print("\n[2/6] Running quality gates...")

    gates = [
        ("Ruff lint", ["python", "-m", "ruff", "check", "."]),
        ("Ruff format", ["python", "-m", "ruff", "format", "--check", "."]),
        ("Pytest", ["python", "-m", "pytest", "-q", "--tb=line"]),
        ("Git diff", ["git", "diff", "--check"]),
    ]

    all_pass = True
    for name, cmd in gates:
        print(f"  Checking {name}...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ✗ {name} FAILED")
            print(f"    {result.stdout[:200]}")
            all_pass = False
        else:
            print(f"  ✓ {name} PASSED")

    return all_pass


def create_release_branch(version: str) -> str:
    """Create release branch."""
    branch = f"release/{version}"
    print(f"\n[3/6] Creating release branch: {branch}")
    run_cmd(["git", "checkout", "-b", branch])
    return branch


def create_release_notes(version: str) -> str:
    """Generate release notes from git log."""
    print("\n[4/6] Generating release notes...")

    result = run_cmd(["git", "log", "--oneline", "--no-merges", "-20"])
    commits = result.stdout.strip().split("\n")

    notes = f"""# Release {version}

**Date:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Changes

"""
    for commit in commits:
        if commit.strip():
            notes += f"- {commit}\n"

    notes += """
## Verification

- [ ] All tests pass
- [ ] Ruff lint clean
- [ ] Ruff format clean
- [ ] Migration rollback tested
- [ ] Backup/restore tested
- [ ] Staging smoke tests pass
- [ ] Security review complete
- [ ] Manual acceptance complete

## Deployment

```bash
# Staging
docker compose -f docker-compose.staging.yml up -d
python scripts/staging_smoke.py --base-url http://staging.example.com

# Production (after staging approval)
docker compose up -d
```

## Rollback

```bash
python scripts/rollback.py {version}
```
"""
    return notes


def tag_release(version: str, notes: str) -> None:
    """Create git tag for release."""
    print(f"\n[5/6] Creating tag: {version}")

    # Write notes to temp file
    notes_file = Path("RELEASE_NOTES.md")
    notes_file.write_text(notes)

    run_cmd(["git", "add", "RELEASE_NOTES.md"])
    run_cmd(["git", "commit", "-m", f"chore(release): prepare {version}"])
    run_cmd(["git", "tag", "-a", version, "-m", f"Release {version}"])

    # Clean up
    notes_file.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description="Release script")
    parser.add_argument("version", help="Version tag (e.g., v1.0.0)")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be done")
    parser.add_argument("--skip-tests", action="store_true", help="Skip quality gates")
    args = parser.parse_args()

    os.chdir(Path(__file__).parent.parent)

    print("=" * 60)
    print(f"Release: {args.version}")
    print("=" * 60)

    current = get_current_version()
    print(f"\nCurrent version: {current}")

    if args.dry_run:
        print("\n[DRY RUN] Would:")
        print("  1. Verify quality gates")
        print(f"  2. Create branch release/{args.version}")
        print("  3. Generate release notes")
        print(f"  4. Tag {args.version}")
        return 0

    # Verify gates
    if not args.skip_tests:
        if not verify_gates():
            print("\n✗ Quality gates FAILED. Fix issues before releasing.")
            return 1
        print("\n  ✓ All gates PASSED")
    else:
        print("\n[WARNING] Skipping quality gates")

    # Create release branch
    branch = create_release_branch(args.version)

    # Generate notes
    notes = create_release_notes(args.version)

    # Tag
    try:
        tag_release(args.version, notes)
    except RuntimeError as e:
        print(f"\n✗ Tag creation failed: {e}")
        run_cmd(["git", "checkout", "main"], check=False)
        run_cmd(["git", "branch", "-D", branch], check=False)
        return 1

    print(f"\n✓ Release {args.version} created successfully!")
    print(f"  Branch: {branch}")
    print(f"  Tag: {args.version}")
    print("\nNext steps:")
    print("  1. Review release notes")
    print(f"  2. Push branch and tag: git push origin {branch} {args.version}")
    print("  3. Create PR to merge into main")
    print("  4. After CI passes, merge and deploy")

    return 0


if __name__ == "__main__":
    sys.exit(main())
