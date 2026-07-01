#!/usr/bin/env python3
"""Staging-only Alembic migration rollback smoke check."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "leadflow-migration-rollback-smoke"
DEFAULT_ENV_FILE = "/tmp/leadflow-staging-smoke.env"
COMPOSE_FILE = "docker-compose.staging.yml"


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def assert_staging_only(args: argparse.Namespace) -> None:
    env_values = read_env_file(Path(args.env_file))
    app_env_values = {env_values.get("APP_ENV", ""), os.environ.get("APP_ENV", "")}
    if any(value.lower() == "production" for value in app_env_values):
        raise RuntimeError("Refusing to run migration rollback smoke with APP_ENV=production")
    if "prod" in args.project_name.lower():
        raise RuntimeError("Refusing to run with a project name that looks production-like")
    if Path(args.compose_file).name != COMPOSE_FILE:
        raise RuntimeError(f"Refusing to run without {COMPOSE_FILE}")
    if not args.confirm_staging and not args.dry_run:
        raise RuntimeError("Pass --confirm-staging to run this staging-only smoke check")


def compose_cmd(args: argparse.Namespace, *extra: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-p",
        args.project_name,
        "--env-file",
        args.env_file,
        "-f",
        args.compose_file,
        *extra,
    ]


def run(args: argparse.Namespace, *extra: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = compose_cmd(args, *extra)
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or f"Command failed: {' '.join(cmd)}")
    return result


def alembic(
    args: argparse.Namespace, *extra: str, check: bool = True
) -> subprocess.CompletedProcess:
    return run(args, "run", "--rm", "migrate", "alembic", *extra, check=check)


def revision_token(output: str) -> str:
    for line in output.splitlines():
        line = line.strip()
        if line:
            return line.split()[0]
    return ""


def cleanup(args: argparse.Namespace) -> None:
    if args.keep_resources:
        print("Keeping compose resources because --keep-resources was provided")
        return
    run(args, "down", "-v", "--remove-orphans", check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging migration rollback smoke check")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--compose-file", default=COMPOSE_FILE)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT)
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--keep-resources", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("STAGING MIGRATION ROLLBACK SMOKE CHECK")
    print("=" * 72)

    try:
        assert_staging_only(args)
        if args.dry_run:
            print("DRY RUN: would run alembic current, downgrade -1, upgrade head, current")
            return 0

        run(args, "up", "-d", "db", "redis")
        run(args, "up", "migrate")

        head = revision_token(alembic(args, "heads").stdout)
        before = revision_token(alembic(args, "current").stdout)
        if before != head:
            raise RuntimeError(
                f"Database is not at head before rollback: current={before}, head={head}"
            )

        downgrade = alembic(args, "downgrade", "-1", check=False)
        if downgrade.returncode != 0:
            print("FAIL: alembic downgrade -1 failed; existing migrations may not support rollback")
            print(downgrade.stderr.strip() or downgrade.stdout.strip())
            return 1

        alembic(args, "upgrade", "head")
        after = revision_token(alembic(args, "current").stdout)
        if after != head:
            raise RuntimeError(f"Database did not return to head: current={after}, head={head}")

        print("PASS: alembic downgrade -1 and upgrade head returned database to head")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        if not args.dry_run:
            cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
