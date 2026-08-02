"""Safe structured application logging.

Only operational identifiers are accepted. Secret-like fields and document bodies are
dropped before the event reaches a formatter.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, g, has_request_context

_ALLOWED_FIELDS = {
    "request_id",
    "job_id",
    "mission_id",
    "candidate_id",
    "provider",
    "stage",
    "error_code",
    "duration_ms",
    "url",
}
_SENSITIVE_PARTS = {
    "key",
    "token",
    "secret",
    "password",
    "authorization",
    "cookie",
    "body",
    "html",
}
_SAFE_EVENT_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def _tenant_ref(tenant_id: object) -> str:
    return hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()[:12]


def _safe_url(value: object) -> str | None:
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        port = f":{parsed.port}" if parsed.port is not None else ""
    except ValueError:
        return None
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    return urlunsplit((parsed.scheme.lower(), f"{host}{port}", parsed.path or "/", "", ""))


def safe_event(event: str, *, level: str = "info", **fields: Any) -> dict[str, Any]:
    """Build a JSON-safe event from a small allowlist of operational fields."""

    event_name = str(event)
    if _SAFE_EVENT_NAME.fullmatch(event_name) is None:
        event_name = "application.log"
    output: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": str(level).lower(),
        "event": event_name,
    }
    tenant_id = fields.pop("tenant_id", None)
    if tenant_id:
        output["tenant_ref"] = _tenant_ref(tenant_id)
    if has_request_context() and "request_id" not in fields:
        fields["request_id"] = g.get("request_id", "")
    for name, value in fields.items():
        clean_name = str(name).lower()
        if any(part in clean_name for part in _SENSITIVE_PARTS):
            continue
        if clean_name not in _ALLOWED_FIELDS or value is None or value == "":
            continue
        if clean_name == "url":
            value = _safe_url(value)
            if value is None:
                continue
        elif clean_name == "duration_ms":
            value = max(0, int(value))
        else:
            value = str(value)[:200]
        output[clean_name] = value
    return output


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "safe_fields", {})
        if not isinstance(fields, dict):
            fields = {}
        return json.dumps(
            safe_event(record.getMessage(), level=record.levelname, **fields),
            ensure_ascii=False,
            separators=(",", ":"),
        )


def configure_logging(app: Flask) -> None:
    """Install a single safe JSON handler on the application logger."""

    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False
