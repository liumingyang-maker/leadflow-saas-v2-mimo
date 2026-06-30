"""Tests for Docker configuration hardening."""

from __future__ import annotations

import os


class TestDockerfileHardening:
    """Dockerfile MUST follow security best practices."""

    def test_non_root_user_configured(self) -> None:
        with open("Dockerfile") as f:
            content = f.read()
        assert "USER leadflow" in content, "Dockerfile must run as non-root user"

    def test_user_created(self) -> None:
        with open("Dockerfile") as f:
            content = f.read()
        assert "useradd" in content or "adduser" in content, "Dockerfile must create a user"

    def test_healthcheck_configured(self) -> None:
        with open("Dockerfile") as f:
            content = f.read()
        assert "HEALTHCHECK" in content

    def test_no_root_user_in_cmd(self) -> None:
        """CMD should not explicitly run as root."""
        with open("Dockerfile") as f:
            content = f.read()
        # USER leadflow is set before CMD, so CMD runs as leadflow
        user_line = content.find("USER leadflow")
        cmd_line = content.find("CMD")
        assert user_line < cmd_line, "USER must be set before CMD"


class TestDockerComposeConfig:
    """docker-compose.yml MUST have healthchecks for all services."""

    def test_all_services_have_healthchecks(self) -> None:
        import yaml

        with open("docker-compose.yml") as f:
            config = yaml.safe_load(f)
        for name, svc in config.get("services", {}).items():
            if name == "worker":
                continue  # Worker doesn't serve HTTP
            assert "healthcheck" in svc, f"Service {name} missing healthcheck"

    def test_redis_image_pinned(self) -> None:
        import yaml

        with open("docker-compose.yml") as f:
            config = yaml.safe_load(f)
        redis = config["services"]["redis"]
        image = redis.get("image", "")
        assert ":" in image, "Redis image should be version-pinned"
        assert "alpine" in image, "Redis should use alpine variant"


class TestStagingCompose:
    """docker-compose.staging.yml MUST exist and use PostgreSQL."""

    def test_staging_compose_exists(self) -> None:
        assert os.path.isfile("docker-compose.staging.yml")

    def test_staging_uses_postgres(self) -> None:
        import yaml

        with open("docker-compose.staging.yml") as f:
            config = yaml.safe_load(f)
        assert "db" in config["services"]
        db_image = config["services"]["db"].get("image", "")
        assert "postgres" in db_image

    def test_staging_no_hardcoded_secrets(self) -> None:
        with open("docker-compose.staging.yml") as f:
            content = f.read()
        # Secrets should use ${VAR} references, not hardcoded values
        assert "SECRET_KEY=${SECRET_KEY}" in content
        assert "TENANT_SECRET_KEY=${TENANT_SECRET_KEY}" in content
        assert "dev-only-change-me" not in content

    def test_staging_services_have_restart_policy(self) -> None:
        import yaml

        with open("docker-compose.staging.yml") as f:
            config = yaml.safe_load(f)
        for name, svc in config.get("services", {}).items():
            assert "restart" in svc, f"Service {name} missing restart policy"

    def test_staging_all_services_have_healthchecks(self) -> None:
        import yaml

        with open("docker-compose.staging.yml") as f:
            config = yaml.safe_load(f)
        for name, svc in config.get("services", {}).items():
            if name == "worker":
                continue  # Worker doesn't serve HTTP
            assert "healthcheck" in svc, f"Service {name} missing healthcheck"

    def test_staging_web_and_worker_use_staging_env_and_postgres(self) -> None:
        import yaml

        with open("docker-compose.staging.yml") as f:
            config = yaml.safe_load(f)
        for name in ("web", "worker"):
            env = config["services"][name]["environment"]
            assert "APP_ENV=staging" in env
            assert any(item.startswith("DATABASE_URL=postgresql://") for item in env)
            assert "REDIS_URL=redis://redis:6379/0" in env
