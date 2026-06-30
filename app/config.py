from __future__ import annotations

import os
from typing import ClassVar, Literal

type ConfigName = Literal["development", "testing", "staging", "production"]


class BaseConfig:
    SECRET_KEY: ClassVar[str] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.environ.get(
        "DATABASE_URL", "sqlite:///leadflow-v2-dev.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict[str, object]] = {"future": True}
    REDIS_URL: ClassVar[str] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    PROXY_FIX_HOPS: ClassVar[str | int] = os.environ.get("PROXY_FIX_HOPS", 0)
    SERVER_NAME: ClassVar[str | None] = os.environ.get("SERVER_NAME") or None
    ALLOWED_HOSTS: ClassVar[str] = os.environ.get("ALLOWED_HOSTS", "")
    INBOUND_TOKEN_KEY: ClassVar[str] = os.environ.get("INBOUND_TOKEN_KEY", "")
    OUTREACH_SIGNING_KEY: ClassVar[str] = os.environ.get("OUTREACH_SIGNING_KEY", "")
    TESTING: ClassVar[bool] = False
    DEBUG: ClassVar[bool] = False
    WTF_CSRF_ENABLED: ClassVar[bool] = True
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    SESSION_COOKIE_SECURE: ClassVar[bool] = False
    MAX_CONTENT_LENGTH: ClassVar[int] = 20 * 1024 * 1024


class DevelopmentConfig(BaseConfig):
    DEBUG: ClassVar[bool] = True
    INBOUND_TOKEN_KEY: ClassVar[str] = os.environ.get(
        "INBOUND_TOKEN_KEY", "development-inbound-token-key-not-for-production"
    )
    OUTREACH_SIGNING_KEY: ClassVar[str] = os.environ.get(
        "OUTREACH_SIGNING_KEY", "development-outreach-signing-key-not-for-production"
    )


class TestingConfig(BaseConfig):
    TESTING: ClassVar[bool] = True
    WTF_CSRF_ENABLED: ClassVar[bool] = False
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = "sqlite:///:memory:"
    SECRET_KEY: ClassVar[str] = os.environ.get(
        "SECRET_KEY", "testing-secret-key-not-for-production"
    )
    INBOUND_TOKEN_KEY: ClassVar[str] = os.environ.get(
        "INBOUND_TOKEN_KEY", "testing-inbound-token-key-not-for-production"
    )
    OUTREACH_SIGNING_KEY: ClassVar[str] = os.environ.get(
        "OUTREACH_SIGNING_KEY", "testing-outreach-signing-key-not-for-production"
    )


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE: ClassVar[bool] = True
    PREFERRED_URL_SCHEME: ClassVar[str] = "https"


class StagingConfig(ProductionConfig):
    DEBUG: ClassVar[bool] = False


CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
    "staging": StagingConfig,
    "stage": StagingConfig,
    "production": ProductionConfig,
    "prod": ProductionConfig,
}

WEAK_SECRET_KEYS = {
    "",
    "dev",
    "secret",
    "change-me",
    "dev-only-change-me",
    "testing-secret-key-not-for-production",
    "development-inbound-token-key-not-for-production",
    "testing-inbound-token-key-not-for-production",
    "development-outreach-signing-key-not-for-production",
    "testing-outreach-signing-key-not-for-production",
}


def _validate_deploy_config(config_class: type[BaseConfig], env_name: str) -> None:
    secret_key = os.environ.get("SECRET_KEY", "")
    if not secret_key:
        raise RuntimeError(f"SECRET_KEY is required for {env_name} configuration")
    if secret_key.strip().lower() in WEAK_SECRET_KEYS or len(secret_key) < 32:
        raise RuntimeError(f"SECRET_KEY is weak for {env_name} configuration")

    tenant_secret_key = os.environ.get("TENANT_SECRET_KEY", "")
    if not tenant_secret_key:
        raise RuntimeError(f"TENANT_SECRET_KEY is required for {env_name} configuration")
    if tenant_secret_key.strip().lower() in WEAK_SECRET_KEYS or len(tenant_secret_key) < 32:
        raise RuntimeError(f"TENANT_SECRET_KEY is weak for {env_name} configuration")

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError(f"DATABASE_URL is required for {env_name} configuration")
    if database_url.startswith("sqlite:"):
        raise RuntimeError(f"DATABASE_URL must use PostgreSQL for {env_name} configuration")

    redis_url = os.environ.get("REDIS_URL", "")
    if not redis_url:
        raise RuntimeError(f"REDIS_URL is required for {env_name} configuration")

    inbound_token_key = os.environ.get("INBOUND_TOKEN_KEY", "")
    if not inbound_token_key:
        raise RuntimeError(f"INBOUND_TOKEN_KEY is required for {env_name} configuration")
    if inbound_token_key.strip().lower() in WEAK_SECRET_KEYS or len(inbound_token_key) < 32:
        raise RuntimeError(f"INBOUND_TOKEN_KEY is weak for {env_name} configuration")

    outreach_signing_key = os.environ.get("OUTREACH_SIGNING_KEY", "")
    if not outreach_signing_key:
        raise RuntimeError(f"OUTREACH_SIGNING_KEY is required for {env_name} configuration")
    if outreach_signing_key.strip().lower() in WEAK_SECRET_KEYS or len(outreach_signing_key) < 32:
        raise RuntimeError(f"OUTREACH_SIGNING_KEY is weak for {env_name} configuration")

    config_class.SECRET_KEY = secret_key
    config_class.SQLALCHEMY_DATABASE_URI = database_url
    config_class.REDIS_URL = redis_url
    config_class.PROXY_FIX_HOPS = os.environ.get("PROXY_FIX_HOPS", 0)
    config_class.SERVER_NAME = os.environ.get("SERVER_NAME") or None
    config_class.ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "")
    config_class.INBOUND_TOKEN_KEY = inbound_token_key
    config_class.OUTREACH_SIGNING_KEY = outreach_signing_key


def resolve_config(config_name: str | None = None) -> type[BaseConfig]:
    name = (config_name or os.environ.get("APP_ENV") or "development").lower()
    try:
        config_class = CONFIGS[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(CONFIGS))
        raise RuntimeError(
            f"Unknown APP_ENV/config name {name!r}. Expected one of: {allowed}"
        ) from exc

    if config_class in {StagingConfig, ProductionConfig}:
        env_label = "staging" if config_class is StagingConfig else "production"
        _validate_deploy_config(config_class, env_label)

    return config_class
