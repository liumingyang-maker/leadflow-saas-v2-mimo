from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

ACQUISITION_PROVIDERS = ("disabled", "fake", "brave")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class AcquisitionProviderSettings(Base):
    __tablename__ = "acquisition_provider_settings"
    __table_args__ = (
        CheckConstraint(
            "provider in ('disabled', 'fake', 'brave')",
            name="acquisition_provider_settings_provider",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="disabled", nullable=False)
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    api_key_last4: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    daily_spend_cap_cents: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    query_limit_per_run: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    result_limit_per_run: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    last_error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
