from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_requirements_include_data_layer_dependencies() -> None:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "SQLAlchemy" in requirements
    assert "Alembic" in requirements
    assert "psycopg2-binary>=2.9,<3" in requirements


def test_runtime_lock_includes_postgres_driver() -> None:
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")

    assert "psycopg2-binary==" in lock
