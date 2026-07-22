"""Payment domain models: Coupon, Payment, PaymentEvent."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


def _hex() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Coupon(Base):
    """Discount coupon that can be applied to tenant subscriptions."""

    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("code", name="uq_coupons_code"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class Payment(Base):
    """Payment record for a tenant subscription or one-time purchase."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="stripe")
    provider_payment_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    plan: Mapped[str] = mapped_column(String(32), nullable=False, default="pro")
    coupon_id: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class PaymentEvent(Base):
    """Webhook event log for payment provider callbacks."""

    __tablename__ = "payment_events"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="uq_payment_events_provider_event"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_id: Mapped[str | None] = mapped_column(String(64), index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    signature_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
