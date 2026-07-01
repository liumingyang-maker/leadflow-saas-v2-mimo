from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from flask import Flask
from redis import Redis


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    count: int
    key: str


def rate_limit_hit(
    app: Flask,
    *,
    namespace: str,
    identifiers: list[str],
    limit: int,
    window_seconds: int,
) -> RateLimitDecision:
    key = _rate_limit_key(namespace, identifiers)
    if _use_memory_store(app):
        return _memory_hit(app, key=key, limit=limit, window_seconds=window_seconds)

    try:
        client = Redis.from_url(str(app.config["REDIS_URL"]))
        count = int(client.incr(key))
        if count == 1:
            client.expire(key, window_seconds)
        return RateLimitDecision(allowed=count <= limit, count=count, key=key)
    except Exception:
        return RateLimitDecision(allowed=False, count=limit + 1, key=key)


def rate_limit_clear(app: Flask, *, namespace: str, identifiers: list[str]) -> None:
    key = _rate_limit_key(namespace, identifiers)
    if _use_memory_store(app):
        _memory_store(app).pop(key, None)
        return
    try:
        Redis.from_url(str(app.config["REDIS_URL"])).delete(key)
    except Exception:
        return


def rate_limit_exceeded(
    app: Flask,
    *,
    namespace: str,
    identifiers: list[str],
    limit: int,
) -> bool:
    key = _rate_limit_key(namespace, identifiers)
    if _use_memory_store(app):
        count, expires_at = _memory_store(app).get(key, (0, 0.0))
        if expires_at <= time.time():
            _memory_store(app).pop(key, None)
            return False
        return count >= limit
    try:
        value = Redis.from_url(str(app.config["REDIS_URL"])).get(key)
    except Exception:
        return True
    return int(value or 0) >= limit


def rate_limit_key_for_tests(namespace: str, identifiers: list[str]) -> str:
    return _rate_limit_key(namespace, identifiers)


def _rate_limit_key(namespace: str, identifiers: list[str]) -> str:
    normalized = ":".join((item or "").strip().lower() for item in identifiers)
    digest = hashlib.sha256(f"{namespace}:{normalized}".encode()).hexdigest()
    return f"leadflow:rate-limit:{namespace}:{digest}"


def _use_memory_store(app: Flask) -> bool:
    return bool(app.config.get("TESTING") or app.config.get("DEBUG"))


def _memory_store(app: Flask) -> dict[str, tuple[int, float]]:
    return app.extensions.setdefault("abuse_rate_limits", {})


def _memory_hit(
    app: Flask,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> RateLimitDecision:
    now = time.time()
    store = _memory_store(app)
    count, expires_at = store.get(key, (0, 0.0))
    if expires_at <= now:
        count = 0
        expires_at = now + window_seconds
    count += 1
    store[key] = (count, expires_at)
    return RateLimitDecision(allowed=count <= limit, count=count, key=key)
