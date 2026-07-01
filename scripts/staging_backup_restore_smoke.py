#!/usr/bin/env python3
"""Staging-only PostgreSQL backup/restore smoke check.

Creates a dump from an ephemeral staging compose project, restores it into a
separate restore_check database, verifies key tables, and cleans up resources.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "leadflow-backup-restore-smoke"
DEFAULT_ENV_FILE = "/tmp/leadflow-staging-smoke.env"
COMPOSE_FILE = "docker-compose.staging.yml"
RESTORE_DATABASE = "restore_check"
REQUIRED_TABLES = ("alembic_version", "tenants", "users", "jobs", "leads")


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
        raise RuntimeError("Refusing to run staging backup/restore smoke with APP_ENV=production")
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
        raise RuntimeError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
    return result


def dump_database(args: argparse.Namespace, dump_path: Path) -> None:
    cmd = compose_cmd(
        args, "exec", "-T", "db", "pg_dump", "-U", "leadflow", "-d", "leadflow", "-Fc"
    )
    print(f"$ {' '.join(cmd)} > {dump_path}")
    with dump_path.open("wb") as dump_file:
        result = subprocess.run(cmd, cwd=ROOT, stdout=dump_file, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    if dump_path.stat().st_size == 0:
        raise RuntimeError("pg_dump produced an empty backup file")


def restore_database(args: argparse.Namespace, dump_path: Path) -> None:
    run(args, "exec", "-T", "db", "dropdb", "-U", "leadflow", "--if-exists", RESTORE_DATABASE)
    run(args, "exec", "-T", "db", "createdb", "-U", "leadflow", RESTORE_DATABASE)
    cmd = compose_cmd(
        args,
        "exec",
        "-T",
        "db",
        "pg_restore",
        "-U",
        "leadflow",
        "-d",
        RESTORE_DATABASE,
    )
    print(f"$ {' '.join(cmd)} < {dump_path}")
    with dump_path.open("rb") as dump_file:
        result = subprocess.run(cmd, cwd=ROOT, stdin=dump_file, stderr=subprocess.PIPE)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())


def verify_tables(args: argparse.Namespace) -> None:
    for table in REQUIRED_TABLES:
        query = f"select to_regclass('public.{table}') is not null;"
        result = run(
            args,
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "leadflow",
            "-d",
            RESTORE_DATABASE,
            "-tAc",
            query,
        )
        if result.stdout.strip() != "t":
            raise RuntimeError(f"Restored database is missing required table: {table}")


def cleanup(args: argparse.Namespace) -> None:
    if args.keep_resources:
        print("Keeping compose resources because --keep-resources was provided")
        return
    run(
        args,
        "exec",
        "-T",
        "db",
        "dropdb",
        "-U",
        "leadflow",
        "--if-exists",
        RESTORE_DATABASE,
        check=False,
    )
    run(args, "down", "-v", "--remove-orphans", check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging backup/restore smoke check")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    parser.add_argument("--compose-file", default=COMPOSE_FILE)
    parser.add_argument("--project-name", default=DEFAULT_PROJECT)
    parser.add_argument("--confirm-staging", action="store_true")
    parser.add_argument("--keep-resources", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("STAGING BACKUP/RESTORE SMOKE CHECK")
    print("=" * 72)

    try:
        assert_staging_only(args)
        if args.dry_run:
            print(
                "DRY RUN: would start staging compose, pg_dump, pg_restore, verify tables, cleanup"
            )
            return 0

        with tempfile.TemporaryDirectory(prefix="leadflow-backup-restore-") as tmp_dir:
            dump_path = Path(tmp_dir) / "leadflow.dump"
            run(args, "up", "-d", "db", "redis")
            run(args, "up", "migrate")
            dump_database(args, dump_path)
            restore_database(args, dump_path)
            verify_tables(args)
            print("PASS: backup restored into restore_check and required tables verified")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        if not args.dry_run:
            cleanup(args)


if __name__ == "__main__":
    sys.exit(main())
