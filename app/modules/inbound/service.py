"""Inbound service — token generation, API security, rate limiting."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.inbound.models import (
    InboundAllowedOrigin,
    InboundIdempotency,
    InboundRateLimit,
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


def _derive_key() -> Fernet:
    raw = os.environ.get("INBOUND_TOKEN_KEY", "dev-inbound-key-32-chars-min!!")
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
    cipher = _derive_key().encrypt(plaintext.encode()).decode()
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
    """Atomic rate limit check using UPDATE ... WHERE to prevent lost updates."""
    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    now = datetime.now(UTC)
    window_end = now + timedelta(seconds=RATE_LIMIT_WINDOW_SECONDS)

    with _session(app) as session:
        # Try atomic increment: only succeeds if record exists, not expired, under limit
        result = session.execute(
            update(InboundRateLimit)
            .where(
                InboundRateLimit.scope == scope,
                InboundRateLimit.bucket == bucket,
                InboundRateLimit.reset_at > now,
                InboundRateLimit.count < RATE_LIMIT_COUNT,
            )
            .values(count=InboundRateLimit.count + 1)
        )
        if result.rowcount > 0:
            session.commit()
            return True

        # Try atomic reset of expired window
        reset_result = session.execute(
            update(InboundRateLimit)
            .where(
                InboundRateLimit.scope == scope,
                InboundRateLimit.bucket == bucket,
                InboundRateLimit.reset_at <= now,
            )
            .values(count=1, reset_at=window_end)
        )
        if reset_result.rowcount > 0:
            session.commit()
            return True

        # Check if record exists and limit reached
        record = session.scalar(
            select(InboundRateLimit).where(
                InboundRateLimit.scope == scope, InboundRateLimit.bucket == bucket
            )
        )
        if record is not None:
            # Limit reached (record exists, not expired, count >= limit)
            return False

        # No record: create new bucket
        from sqlalchemy.exc import IntegrityError

        try:
            new_record = InboundRateLimit(
                scope=scope,
                bucket=bucket,
                count=1,
                reset_at=window_end,
            )
            session.add(new_record)
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            # Another process created it; try atomic increment once
            retry_result = session.execute(
                update(InboundRateLimit)
                .where(
                    InboundRateLimit.scope == scope,
                    InboundRateLimit.bucket == bucket,
                    InboundRateLimit.reset_at > now,
                    InboundRateLimit.count < RATE_LIMIT_COUNT,
                )
                .values(count=InboundRateLimit.count + 1)
            )
            if retry_result.rowcount > 0:
                session.commit()
                return True
            return False


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------
IDEMPOTENCY_TTL_HOURS = 24
FINGERPRINT_WINDOW_MINUTES = 5


PROCESSING_LEASE_SECONDS = 30


def check_idempotency(
    app: Flask, *, tenant_id: str, token_digest: str, idempotency_key: str, payload: dict[str, Any]
) -> tuple[str, str | None, str]:
    """Pre-occupy pattern with lease and claim_token.

    Returns (status, response_json or None, claim_token).
    'new' means this caller owns processing rights (claim_token is valid).
    'replayed' means a completed result exists.
    'processing' means another caller holds a valid lease.
    'conflict' means same key but different payload.
    """
    import uuid

    from sqlalchemy import update
    from sqlalchemy.exc import IntegrityError

    now = datetime.now(UTC)
    payload_str = json.dumps(payload, sort_keys=True)
    payload_digest = hashlib.sha256(payload_str.encode()).hexdigest()
    lease_end = now + timedelta(seconds=PROCESSING_LEASE_SECONDS)

    effective_key = idempotency_key or inbound_fingerprint_key(
        token_digest=token_digest, payload=payload
    )
    claim = uuid.uuid4().hex
    # Explicit keys get 24h TTL; fingerprints get 5min window
    ttl = (
        timedelta(hours=IDEMPOTENCY_TTL_HOURS)
        if idempotency_key
        else timedelta(minutes=FINGERPRINT_WINDOW_MINUTES)
    )

    with _session(app) as session:
        # Try to pre-occupy: insert a "processing" record with lease
        try:
            record = InboundIdempotency(
                tenant_id=tenant_id,
                token_digest=token_digest,
                idempotency_key=effective_key,
                payload_digest=payload_digest,
                status="processing",
                claim_token=claim,
                response_json="{}",
                expires_at=now + ttl,
                processing_expires_at=lease_end,
            )
            session.add(record)
            session.commit()
            return "new", None, claim
        except IntegrityError:
            session.rollback()

        # Record already exists - read it
        existing = session.scalar(
            select(InboundIdempotency).where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == effective_key,
            )
        )
        if existing is None:
            # Fail closed: cannot verify ownership without a record
            return "processing", None, ""

        # Payload conflict is unconditional (same key must mean same content)
        if existing.payload_digest != payload_digest:
            return "conflict", None, ""

        # Processing with valid lease
        if existing.status == "processing":
            proc_expires = existing.processing_expires_at
            if proc_expires is not None and _as_utc(proc_expires) > now:
                return "processing", None, ""
            # Lease expired or NULL: try to take over with conditional UPDATE
            from sqlalchemy import or_

            result = session.execute(
                update(InboundIdempotency)
                .where(
                    InboundIdempotency.tenant_id == tenant_id,
                    InboundIdempotency.token_digest == token_digest,
                    InboundIdempotency.idempotency_key == effective_key,
                    InboundIdempotency.status == "processing",
                    or_(
                        InboundIdempotency.processing_expires_at.is_(None),
                        InboundIdempotency.processing_expires_at <= now,
                    ),
                )
                .values(
                    claim_token=claim,
                    processing_expires_at=lease_end,
                )
            )
            if result.rowcount > 0:
                session.commit()
                return "new", None, claim
            # Another process took over first
            return "processing", None, ""

        # Completed and not expired: replay
        if _as_utc(existing.expires_at) > now:
            return "replayed", existing.response_json, ""

        # Expired completed: re-claim with conditional UPDATE
        result = session.execute(
            update(InboundIdempotency)
            .where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == effective_key,
                InboundIdempotency.expires_at <= now,
            )
            .values(
                status="processing",
                claim_token=claim,
                payload_digest=payload_digest,
                response_json="{}",
                expires_at=now + ttl,
                processing_expires_at=lease_end,
            )
        )
        if result.rowcount > 0:
            session.commit()
            return "new", None, claim
        return "processing", None, ""


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
    claim_token: str,
) -> bool:
    """Update the pre-occupied record with final result, verifying ownership.

    Returns True if the update succeeded (ownership confirmed).
    Returns False if the lease was lost (another process took over).
    """
    from sqlalchemy import update

    if not claim_token:
        raise ValueError("claim_token is required for store_idempotency")

    now = datetime.now(UTC)
    effective_key = idempotency_key or inbound_fingerprint_key(
        token_digest=token_digest, payload=payload
    )
    with _session(app) as session:
        result = session.execute(
            update(InboundIdempotency)
            .where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == effective_key,
                InboundIdempotency.status == "processing",
                InboundIdempotency.claim_token == claim_token,
            )
            .values(
                status=status,
                response_json=json.dumps(response),
                expires_at=now + timedelta(hours=IDEMPOTENCY_TTL_HOURS),
                processing_expires_at=None,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            return False
        session.commit()
        return True


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


def _process_inbound_inner(
    session: Session, *, tenant_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Core inbound logic within an existing session. Does NOT commit."""
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
            last_name=(data.get("last_name") or (parts[1] if len(parts) > 1 else "") or "")[:120],
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
    return {"ok": True, "id": lead.id}


def process_inbound(
    app: Flask,
    *,
    tenant_id: str,
    token_digest: str,
    body: dict[str, Any],
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Standalone inbound processing (commits independently). Legacy interface."""
    if body.get("hp_field"):
        return {"ok": True, "id": "accepted"}
    data = {
        k: v
        for k, v in body.items()
        if k in ALLOWED_FIELDS and k not in ("idempotency_key", "hp_field")
    }
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "invalid_email"}

    with _session(app) as session:
        result = _process_inbound_inner(session, tenant_id=tenant_id, body=body)
        if result.get("ok"):
            session.commit()
        return result


def process_and_finalize(
    app: Flask,
    *,
    tenant_id: str,
    token_digest: str,
    body: dict[str, Any],
    idempotency_key: str,
    storage_key: str,
    claim_token: str,
) -> tuple[dict[str, Any], bool]:
    """Single transaction: renew lease + business logic + idempotency finalize.

    Returns (result, ownership_held). If ownership_held is False, the
    transaction was rolled back and no side effects occurred.
    """
    from sqlalchemy import update

    now = datetime.now(UTC)
    ttl = (
        timedelta(hours=IDEMPOTENCY_TTL_HOURS)
        if idempotency_key
        else timedelta(minutes=FINGERPRINT_WINDOW_MINUTES)
    )

    with _session(app) as session:
        # 1. Renew lease (prevents expiry during processing)
        renew = session.execute(
            update(InboundIdempotency)
            .where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == storage_key,
                InboundIdempotency.status == "processing",
                InboundIdempotency.claim_token == claim_token,
            )
            .values(processing_expires_at=now + timedelta(seconds=PROCESSING_LEASE_SECONDS))
        )
        if renew.rowcount != 1:
            session.rollback()
            return {"ok": False, "error": "lease_lost"}, False

        # 2. Execute business logic (no independent commit)
        result = _process_inbound_inner(session, tenant_id=tenant_id, body=body)

        # 3. Finalize idempotency record
        final = session.execute(
            update(InboundIdempotency)
            .where(
                InboundIdempotency.tenant_id == tenant_id,
                InboundIdempotency.token_digest == token_digest,
                InboundIdempotency.idempotency_key == storage_key,
                InboundIdempotency.status == "processing",
                InboundIdempotency.claim_token == claim_token,
            )
            .values(
                status="completed" if result.get("ok") else "failed",
                response_json=json.dumps(result),
                expires_at=now + ttl,
                processing_expires_at=None,
            )
        )
        if final.rowcount != 1:
            session.rollback()
            return result, False

        # 4. Commit everything atomically
        session.commit()
        return result, True


def _inbound_notes(data: dict[str, Any]) -> str:
    parts: list[str] = []
    company = (data.get("company") or "").strip()
    message = (data.get("message") or "").strip()
    if company:
        parts.append(f"Company: {company}")
    if message:
        parts.append(f"Message: {message}")
    return "\n".join(parts)[:5000]
