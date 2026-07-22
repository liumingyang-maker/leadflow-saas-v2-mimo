from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_installs_runtime_dependencies_and_uses_factory() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "FLASK_APP=app:create_app" in dockerfile
    assert "/health/live" in dockerfile
    assert '"flask"' in dockerfile
    assert '"run"' in dockerfile


def test_compose_defines_web_and_redis_for_development() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "web:" in compose
    assert "redis:" in compose
    assert "APP_ENV=development" in compose
    assert "SECRET_KEY=dev-only-change-me" in compose
    assert "DATABASE_URL=sqlite:////data/leadflow-v2.db" in compose
    assert "REDIS_URL=redis://redis:6379/0" in compose
    assert "5000:5000" in compose
    assert "/health/live" in compose


def test_dockerignore_excludes_local_runtime_artifacts() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for ignored in [
        ".git",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        ".autopilot/logs",
        ".autopilot/screenshots",
        ".autopilot/controller-output",
    ]:
        assert ignored in dockerignore
