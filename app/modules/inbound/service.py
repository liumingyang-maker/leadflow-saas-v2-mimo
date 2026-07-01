"""Inbound service — token generation, API security, rate limiting."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.abuse import rate_limit_hit
from app.extensions import get_engine
from app.modules.inbound.models import (
    InboundAllowedOrigin,
    InboundIdempotency,
    InboundToken,
)
from app.modules.leads.models import Activity, Lead
from app.modules.leads.repository import LeadRepository


class InboundError(ValueError):
    pass


def _session(app: Flask) -> Session:
    s = Session(get_engine(app))
    s.expire_on_commit = False
    return s


def _derive_key(app: Flask) -> Fernet:
    raw = str(app.config.get("INBOUND_TOKEN_KEY", ""))
    if not raw:
        raise InboundError("INBOUND_TOKEN_KEY is not configured")
    digest = hashlib.sha256(raw.encode()).digest()
    import base64

    return Fernet(base64.urlsafe_b64encode(digest))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# ---------------------------------------------------------------------------
# Token management
# ---------------------------------------------------------------------------


def generate_token(app: Flask, *, tenant_id: str) -> tuple[InboundToken, str]:
    plaintext = secrets.token_urlsafe(48)
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    cipher = _derive_key(app).encrypt(plaintext.encode()).decode()
    with _session(app) as session:
        # Deactivate old tokens
        for old in session.scalars(
            select(InboundToken).where(InboundToken.tenant_id == tenant_id, InboundToken.is_active)
        ):
            old.is_active = False
            old.rotated_at = datetime.now(UTC)
        token = InboundToken(
            tenant_id=tenant_id, token_digest=digest, token_ciphertext=cipher, is_active=True
        )
        session.add(token)
        session.commit()
        return token, plaintext


def lookup_token(app: Flask, *, plaintext: str) -> InboundToken | None:
    digest = hashlib.sha256(plaintext.encode()).hexdigest()
    with _session(app) as session:
        return session.scalar(
            select(InboundToken).where(InboundToken.token_digest == digest, InboundToken.is_active)
        )


def get_token_info(app: Flask, *, tenant_id: str) -> InboundToken | None:
    with _session(app) as session:
        return session.scalar(
            select(InboundToken).where(InboundToken.tenant_id == tenant_id, InboundToken.is_active)
        )


# ---------------------------------------------------------------------------
# Origin allowlist
# ---------------------------------------------------------------------------
ALLOWED_FIELDS = {
    "email",
    "name",
    "first_name",
    "last_name",
    "company",
    "phone",
    "website",
    "message",
    "source",
    "idempotency_key",
    "hp_field",
}
MAX_BODY_SIZE = 32 * 1024


def list_origins(app: Flask, *, tenant_id: str) -> list[InboundAllowedOrigin]:
    with _session(app) as session:
        return list(
            session.scalars(
                select(InboundAllowedOrigin).where(InboundAllowedOrigin.tenant_id == tenant_id)
            )
        )


def add_origin(app: Flask, *, tenant_id: str, origin: str) -> InboundAllowedOrigin:
    if not origin.startswith(("http://", "https://")):
        raise InboundError("Origin must start with http:// or https://")
    if "/" in origin[8:]:
        raise InboundError("Origin must not include path")
    with _session(app) as session:
        existing = session.scalar(
            select(InboundAllowedOrigin).where(
                InboundAllowedOrigin.tenant_id == tenant_id, InboundAllowedOrigin.origin == origin
            )
        )
        if existing:
            raise InboundError("Origin already exists")
        o = InboundAllowedOrigin(tenant_id=tenant_id, origin=origin)
        session.add(o)
        session.commit()
        return o


def remove_origin(app: Flask, *, tenant_id: str, origin_id: str) -> None:
    with _session(app) as session:
        o = session.get(InboundAllowedOrigin, origin_id)
        if o and o.tenant_id == tenant_id:
            session.delete(o)
            session.commit()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
RATE_LIMIT_COUNT = 100
RATE_LIMIT_WINDOW_SECONDS = 3600


def check_rate_limit(app: Flask, *, scope: str, bucket: str) -> bool:
    decision = rate_limit_hit(
        app,
        namespace="inbound-api",
        identifiers=[scope, bucket],
        limit=RATE_LIMIT_COUNT,
        window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    )
    return decision.allowed


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
IDEMPOTENCY_TTL_HOURS = 24
FINGERPRINT_WINDOW_MINUTES = 5


def check_idempotency(
    app: Flask, *, tenant_id: str, token_digest: str, idempotency_key: str, payload: dict[str, Any]
) -> tuple[str, str | None]:
    """Returns (status, response_json or None). 'new' means proceed."""
    now = datetime.now(UTC)
    payload_str = json.dumps(payload, sort_keys=True)
    payload_digest = hashlib.sha256(payload_str.encode()).hexdigest()

    if idempotency_key:
        with _session(app) as session:
            existing = session.scalar(
                select(InboundIdempotency).where(
                    InboundIdempotency.tenant_id == tenant_id,
                    InboundIdempotency.token_digest == token_digest,
                    InboundIdempotency.idempotency_key == idempotency_key,
                )
            )
            if existing:
                if existing.payload_digest == payload_digest and _as_utc(existing.expires_at) > now:
                    return "replayed", existing.response_json
                return "conflict", None
        return "new", None

    fingerprint = inbound_fingerprint_key(token_digest=token_digest, payload=payload)
    with _session(app) as session:
        existing = session.scalar(
            select(InboundIdempotency).where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == fingerprint,
            )
        )
        if existing and _as_utc(existing.created_at) > now - timedelta(
            minutes=FINGERPRINT_WINDOW_MINUTES
        ):
            return "replayed", existing.response_json
    return "new", None


def inbound_fingerprint_key(*, token_digest: str, payload: dict[str, Any]) -> str:
    payload_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return hashlib.sha256(f"{token_digest}:{payload_digest}".encode()).hexdigest()[:32]


def store_idempotency(
    app: Flask,
    *,
    tenant_id: str,
    token_digest: str,
    idempotency_key: str,
    payload: dict[str, Any],
    status: str,
    response: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    payload_digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with _session(app) as session:
        record = InboundIdempotency(
            tenant_id=tenant_id,
            token_digest=token_digest,
            idempotency_key=idempotency_key,
            payload_digest=payload_digest,
            status=status,
            response_json=json.dumps(response),
            expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
        )
        session.add(record)
        session.commit()


# ---------------------------------------------------------------------------
# Lead creation
# ---------------------------------------------------------------------------


ALLOWED_FIELDS = {
    "email",
    "name",
    "first_name",
    "last_name",
    "company",
    "phone",
    "website",
    "message",
    "source",
    "idempotency_key",
    "hp_field",
}


def process_inbound(
    app: Flask,
    *,
    tenant_id: str,
    token_digest: str,
    body: dict[str, Any],
    idempotency_key: str = "",
) -> dict[str, Any]:
    # Honeypot
    if body.get("hp_field"):
        return {"ok": True, "id": "accepted"}

    # Filter allowed fields
    data = {
        k: v
        for k, v in body.items()
        if k in ALLOWED_FIELDS and k not in ("idempotency_key", "hp_field")
    }
    email = (data.get("email") or "").strip().lower()

    if not email or "@" not in email:
        return {"ok": False, "error": "invalid_email"}

    with _session(app) as session:
        lead_repo = LeadRepository(session)
        # Dedup by email
        existing = list(lead_repo.list(tenant_id=tenant_id, search=email, limit=1))
        if existing:
            lead = existing[0]
        else:
            name = (data.get("name") or data.get("first_name") or "").strip()
            parts = name.split(" ", 1) if name else ("", "")
            lead = Lead(
                tenant_id=tenant_id,
                email=email,
                first_name=(data.get("first_name") or parts[0] or "")[:120],
                last_name=(data.get("last_name") or (parts[1] if len(parts) > 1 else "") or "")[
                    :120
                ],
                phone=(data.get("phone") or "")[:60],
                website=(data.get("website") or "")[:500],
                source="inbound",
                status="pending_review",
                notes=_inbound_notes(data),
            )
            lead_repo.add(lead, tenant_id=tenant_id)
            session.flush()

        session.add(
            Activity(
                tenant_id=tenant_id,
                lead_id=lead.id,
                action="inbound_received",
                description=(
                    "Inbound inquiry" + (" from " + data.get("source", ""))
                    if data.get("source")
                    else ""
                )[:500],
            )
        )
        session.commit()
        return {"ok": True, "id": lead.id}


def _inbound_notes(data: dict[str, Any]) -> str:
    parts: list[str] = []
    company = (data.get("company") or "").strip()
    message = (data.get("message") or "").strip()
    if company:
        parts.append(f"Company: {company}")
    if message:
        parts.append(f"Message: {message}")
    return "\n".join(parts)[:5000]
