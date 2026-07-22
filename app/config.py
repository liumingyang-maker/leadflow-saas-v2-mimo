from __future__ import annotations

import os
from typing import ClassVar, Literal, TypeAlias

ConfigName: TypeAlias = Literal["development", "testing", "production"]


class BaseConfig:
    SECRET_KEY: ClassVar[str] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.environ.get(
        "DATABASE_URL", "sqlite:///leadflow-v2-dev.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict[str, object]] = {"future": True}
    TESTING: ClassVar[bool] = False
    DEBUG: ClassVar[bool] = False
    WTF_CSRF_ENABLED: ClassVar[bool] = True
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    SESSION_COOKIE_SECURE: ClassVar[bool] = False
    MAX_CONTENT_LENGTH: ClassVar[int] = 20 * 1024 * 1024


class DevelopmentConfig(BaseConfig):
    DEBUG: ClassVar[bool] = True


class TestingConfig(BaseConfig):
    TESTING: ClassVar[bool] = True
    WTF_CSRF_ENABLED: ClassVar[bool] = False
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = "sqlite:///:memory:"
    SECRET_KEY: ClassVar[str] = os.environ.get(
        "SECRET_KEY", "testing-secret-key-not-for-production"
    )


class ProductionConfig(BaseConfig):
    SESSION_COOKIE_SECURE: ClassVar[bool] = True
    PREFERRED_URL_SCHEME: ClassVar[str] = "https"


CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "dev": DevelopmentConfig,
    "testing": TestingConfig,
    "test": TestingConfig,
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
    "dev-tracking-sign-key-not-for-prod",
    "dev-unsub-key-not-for-prod",
    "dev-inbound-key-32-chars-min!!",
}


def resolve_config(config_name: str | None = None) -> type[BaseConfig]:
    name = (config_name or os.environ.get("APP_ENV") or "development").lower()
    try:
        config_class = CONFIGS[name]
    except KeyError as exc:
        allowed = ", ".join(sorted(CONFIGS))
        raise RuntimeError(
            f"Unknown APP_ENV/config name {name!r}. Expected one of: {allowed}"
        ) from exc

    if config_class is ProductionConfig:
        secret_key = os.environ.get("SECRET_KEY", "")
        if not secret_key:
            raise RuntimeError("SECRET_KEY is required for production configuration")
        if secret_key.strip().lower() in WEAK_SECRET_KEYS or len(secret_key) < 32:
            raise RuntimeError("SECRET_KEY is weak for production configuration")
        tenant_secret_key = os.environ.get("TENANT_SECRET_KEY", "")
        if not tenant_secret_key:
            raise RuntimeError("TENANT_SECRET_KEY is required for production configuration")
        if len(tenant_secret_key) < 32:
            raise RuntimeError("TENANT_SECRET_KEY is weak for production configuration")
        # Fail closed for all cryptographic keys
        for key_name in (
            "TRACKING_SIGNING_KEY",
            "UNSUBSCRIBE_SIGNING_KEY",
            "INBOUND_TOKEN_KEY",
        ):
            value = os.environ.get(key_name, "")
            if not value or len(value) < 32:
                raise RuntimeError(
                    f"{key_name} is required (>=32 chars) for production configuration"
                )
            if value.strip().lower() in WEAK_SECRET_KEYS:
                raise RuntimeError(f"{key_name} uses a known development default value")
        ProductionConfig.SECRET_KEY = secret_key

    return config_class
