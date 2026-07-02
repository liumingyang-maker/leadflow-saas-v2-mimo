from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

AI_PROVIDERS = ("disabled", "fake", "openai_compatible")
AI_LEDGER_STATUSES = ("success", "failed", "blocked_quota", "disabled")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class AIProviderSettings(Base):
    __tablename__ = "ai_provider_settings"
    __table_args__ = (
        CheckConstraint(
            "provider in ('disabled', 'fake', 'openai_compatible')",
            name="ai_provider_settings_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String(32), default="disabled", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    api_key_last4: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=800, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class TenantAIQuota(Base):
    __tablename__ = "tenant_ai_quotas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), unique=True, nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plan_name: Mapped[str] = mapped_column(String(24), default="basic", nullable=False)
    monthly_included_credits: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class AIUsageLedger(Base):
    __tablename__ = "ai_usage_ledger"
    __table_args__ = (
        CheckConstraint(
            "status in ('success', 'failed', 'blocked_quota', 'disabled')",
            name="ai_usage_ledger_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), default="", nullable=False, index=True)
    feature_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
