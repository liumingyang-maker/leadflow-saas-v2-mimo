"""Tests for production config secret validation."""

from __future__ import annotations

import pytest

from app.config import ProductionConfig, StagingConfig, resolve_config


def _set_deploy_defaults(monkeypatch: pytest.MonkeyPatch, env_name: str) -> None:
    monkeypatch.setenv("APP_ENV", env_name)
    monkeypatch.setenv("SECRET_KEY", "a" * 40)
    monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
    monkeypatch.setenv("DATABASE_URL", "postgresql://leadflow:pass@db:5432/leadflow")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")


class TestProductionSecretValidation:
    """Production config MUST fail on missing or weak secrets."""

    def test_rejects_missing_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
            resolve_config()

    def test_rejects_weak_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.setenv("SECRET_KEY", "short")
        with pytest.raises(RuntimeError, match="SECRET_KEY is weak"):
            resolve_config()

    def test_rejects_dev_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.setenv("SECRET_KEY", "dev-only-change-me")
        with pytest.raises(RuntimeError, match="SECRET_KEY is weak"):
            resolve_config()

    def test_rejects_missing_tenant_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.delenv("TENANT_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is required"):
            resolve_config()

    def test_rejects_weak_tenant_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.setenv("TENANT_SECRET_KEY", "short")
        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is weak"):
            resolve_config()

    def test_accepts_strong_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "production")
        config = resolve_config()
        assert config is ProductionConfig

    def test_error_messages_hide_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error messages must NOT contain the actual secret value."""
        secret = "super-secret-key-value-1234567890123456"
        _set_deploy_defaults(monkeypatch, "production")
        monkeypatch.setenv("SECRET_KEY", secret)
        monkeypatch.setenv("TENANT_SECRET_KEY", "short")
        with pytest.raises(RuntimeError) as exc_info:
            resolve_config()
        assert secret not in str(exc_info.value)


class TestStagingConfigValidation:
    """Staging config follows production-like safety checks."""

    def test_staging_config_is_available(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "staging")

        config = resolve_config("staging")

        assert config is StagingConfig
        assert config.DEBUG is False
        assert config.SESSION_COOKIE_SECURE is True
        assert config.SQLALCHEMY_DATABASE_URI.startswith("postgresql://")

    def test_staging_rejects_missing_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "staging")
        monkeypatch.delenv("SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
            resolve_config("staging")

    def test_staging_rejects_weak_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "staging")
        monkeypatch.setenv("SECRET_KEY", "dev-only-change-me")

        with pytest.raises(RuntimeError, match="SECRET_KEY is weak"):
            resolve_config("staging")

    def test_staging_rejects_missing_tenant_secret_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _set_deploy_defaults(monkeypatch, "staging")
        monkeypatch.delenv("TENANT_SECRET_KEY", raising=False)

        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is required"):
            resolve_config("staging")

    def test_staging_rejects_weak_tenant_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "staging")
        monkeypatch.setenv("TENANT_SECRET_KEY", "short")

        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is weak"):
            resolve_config("staging")

    def test_staging_rejects_sqlite_database_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_deploy_defaults(monkeypatch, "staging")
        monkeypatch.setenv("DATABASE_URL", "sqlite:///leadflow-v2-dev.db")

        with pytest.raises(RuntimeError, match="PostgreSQL"):
            resolve_config("staging")
