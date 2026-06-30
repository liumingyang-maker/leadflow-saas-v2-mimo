"""Tests for production config secret validation."""

from __future__ import annotations

import pytest

from app.config import ProductionConfig, resolve_config


class TestProductionSecretValidation:
    """Production config MUST fail on missing or weak secrets."""

    def test_rejects_missing_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("SECRET_KEY", raising=False)
        monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
        with pytest.raises(RuntimeError, match="SECRET_KEY is required"):
            resolve_config()

    def test_rejects_weak_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "short")
        monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
        with pytest.raises(RuntimeError, match="SECRET_KEY is weak"):
            resolve_config()

    def test_rejects_dev_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "dev-only-change-me")
        monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
        with pytest.raises(RuntimeError, match="SECRET_KEY is weak"):
            resolve_config()

    def test_rejects_missing_tenant_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.delenv("TENANT_SECRET_KEY", raising=False)
        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is required"):
            resolve_config()

    def test_rejects_weak_tenant_secret_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.setenv("TENANT_SECRET_KEY", "short")
        with pytest.raises(RuntimeError, match="TENANT_SECRET_KEY is weak"):
            resolve_config()

    def test_accepts_strong_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", "a" * 40)
        monkeypatch.setenv("TENANT_SECRET_KEY", "b" * 40)
        config = resolve_config()
        assert config is ProductionConfig

    def test_error_messages_hide_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error messages must NOT contain the actual secret value."""
        secret = "super-secret-key-value-1234567890123456"
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("SECRET_KEY", secret)
        monkeypatch.setenv("TENANT_SECRET_KEY", "short")
        with pytest.raises(RuntimeError) as exc_info:
            resolve_config()
        assert secret not in str(exc_info.value)
