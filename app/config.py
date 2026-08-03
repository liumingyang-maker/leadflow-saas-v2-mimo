from __future__ import annotations

import os
from typing import ClassVar, Literal, TypeAlias

from sqlalchemy.engine import URL, make_url
from sqlalchemy.util import asbool

ConfigName: TypeAlias = Literal["development", "testing", "production"]


def _bounded_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _is_file_sqlite_uri(database_uri: str | URL) -> bool:
    url = make_url(database_uri)
    if url.get_backend_name() != "sqlite":
        return False
    database = url.database
    if database in {None, "", ":memory:"}:
        return False
    raw_uri_mode = url.query.get("uri")
    uri_mode = asbool(raw_uri_mode) if raw_uri_mode is not None else False
    return not (
        uri_mode
        and (
            database.casefold().startswith("file::memory:")
            or url.query.get("mode", "").casefold() == "memory"
        )
    )


class BaseConfig:
    SECRET_KEY: ClassVar[str] = os.environ.get("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.environ.get(
        "DATABASE_URL", "sqlite:///leadflow-v2-dev.db"
    )
    SQLALCHEMY_ENGINE_OPTIONS: ClassVar[dict[str, object]] = {"future": True}
    SQLITE_BUSY_TIMEOUT_MS: ClassVar[int] = 5000
    TESTING: ClassVar[bool] = False
    DEBUG: ClassVar[bool] = False
    WTF_CSRF_ENABLED: ClassVar[bool] = True
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"
    SESSION_COOKIE_SECURE: ClassVar[bool] = False
    MAX_CONTENT_LENGTH: ClassVar[int] = 20 * 1024 * 1024
    REDIS_URL: ClassVar[str] = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    MIMO_BASE_URL: ClassVar[str] = os.environ.get("MIMO_BASE_URL", "")
    MIMO_MODEL: ClassVar[str] = os.environ.get("MIMO_MODEL", "mimo-v2.5")
    LOCAL_EMAIL_VERIFICATION: ClassVar[bool] = False
    ACQUISITION_MAX_CANDIDATES: ClassVar[int] = 30
    ACQUISITION_MAX_VERIFY: ClassVar[int] = 10
    ACQUISITION_MAX_SEARCH_ACTIONS: ClassVar[int] = 5
    FETCH_MAX_PAGES_PER_SITE: ClassVar[int] = 5
    FETCH_MAX_BYTES: ClassVar[int] = 1024 * 1024
    FETCH_TIMEOUT_SECONDS: ClassVar[int] = 10
    BROWSER_MAX_PAGES: ClassVar[int] = 10
    BROWSER_MAX_SECONDS: ClassVar[int] = 120
    BROWSER_MAX_TOOL_CALLS: ClassVar[int] = 12
    BROWSER_MAX_ARTIFACT_BYTES: ClassVar[int] = 5 * 1024 * 1024
    BROWSER_REDIS_URL: ClassVar[str] = os.environ.get(
        "BROWSER_REDIS_URL", "redis://localhost:6380/0"
    )


class DevelopmentConfig(BaseConfig):
    DEBUG: ClassVar[bool] = True
    LOCAL_EMAIL_VERIFICATION: ClassVar[bool] = True


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

    config_class.ACQUISITION_MAX_CANDIDATES = _bounded_int(
        "ACQUISITION_MAX_CANDIDATES", 30, minimum=1, maximum=100
    )
    config_class.ACQUISITION_MAX_VERIFY = _bounded_int(
        "ACQUISITION_MAX_VERIFY", 10, minimum=1, maximum=30
    )
    config_class.ACQUISITION_MAX_SEARCH_ACTIONS = _bounded_int(
        "ACQUISITION_MAX_SEARCH_ACTIONS", 5, minimum=1, maximum=20
    )
    config_class.FETCH_MAX_PAGES_PER_SITE = _bounded_int(
        "FETCH_MAX_PAGES_PER_SITE", 5, minimum=1, maximum=10
    )
    config_class.BROWSER_MAX_PAGES = _bounded_int(
        "BROWSER_MAX_PAGES", 10, minimum=1, maximum=25
    )
    config_class.BROWSER_MAX_SECONDS = _bounded_int(
        "BROWSER_MAX_SECONDS", 120, minimum=10, maximum=300
    )
    config_class.BROWSER_MAX_TOOL_CALLS = _bounded_int(
        "BROWSER_MAX_TOOL_CALLS", 12, minimum=1, maximum=30
    )
    config_class.BROWSER_MAX_ARTIFACT_BYTES = _bounded_int(
        "BROWSER_MAX_ARTIFACT_BYTES",
        5 * 1024 * 1024,
        minimum=1024,
        maximum=20 * 1024 * 1024,
    )
    if _is_file_sqlite_uri(config_class.SQLALCHEMY_DATABASE_URI):
        config_class.SQLITE_BUSY_TIMEOUT_MS = _bounded_int(
            "SQLITE_BUSY_TIMEOUT_MS", 5000, minimum=1000, maximum=30000
        )
    else:
        config_class.SQLITE_BUSY_TIMEOUT_MS = 5000
    config_class.REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    config_class.BROWSER_REDIS_URL = os.environ.get(
        "BROWSER_REDIS_URL", "redis://localhost:6380/0"
    )
    config_class.MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "")
    config_class.MIMO_MODEL = os.environ.get("MIMO_MODEL", "mimo-v2.5")

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
