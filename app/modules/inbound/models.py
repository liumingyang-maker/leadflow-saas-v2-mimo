"""Inbound models: InboundToken, InboundAllowedOrigin, InboundRateLimit, InboundIdempotency."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


def _hex() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class InboundToken(Base):
    __tablename__ = "inbound_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_ciphertext: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InboundAllowedOrigin(Base):
    __tablename__ = "inbound_allowed_origins"
    __table_args__ = (
        UniqueConstraint("tenant_id", "origin", name="uq_inbound_origins_tenant_origin"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    origin: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class InboundRateLimit(Base):
    __tablename__ = "inbound_rate_limits"
    __table_args__ = (UniqueConstraint("scope", "bucket", name="uq_rate_limits_scope_bucket"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    scope: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class InboundIdempotency(Base):
    __tablename__ = "inbound_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "token_digest",
            "idempotency_key",
            name="uq_idempotency_tenant_token_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    claim_token: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    response_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processing_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
