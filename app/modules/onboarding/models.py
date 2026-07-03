from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

PRODUCT_PROFILE_STATUSES = ("draft", "extracted", "confirmed", "failed")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class TenantProductProfile(Base):
    __tablename__ = "tenant_product_profiles"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'extracted', 'confirmed', 'failed')",
            name="tenant_product_profiles_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id"), unique=True, nullable=False, index=True
    )
    raw_company_intro: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_products: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_website_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_target_markets: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_advantages: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_certificates: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_moq: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_delivery_capacity: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_customer_countries: Mapped[str] = mapped_column(Text, default="", nullable=False)
    extracted_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
