from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

DISCOVERY_RUN_STATUSES = ("draft", "planned", "matched", "failed")
CANDIDATE_STATUSES = ("pending_review", "added_to_crm", "dismissed", "duplicate", "failed")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class TargetCustomerDiscoveryRun(Base):
    __tablename__ = "target_customer_discovery_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft', 'planned', 'matched', 'failed')",
            name="target_customer_discovery_runs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    product_profile_id: Mapped[str] = mapped_column(
        ForeignKey("tenant_product_profiles.id"), nullable=False, index=True
    )
    filters_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    generated_plan_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    requested_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    generated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_estimated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credits_charged: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class TargetCustomerCandidate(Base):
    __tablename__ = "target_customer_candidates"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending_review', 'added_to_crm', 'dismissed', 'duplicate', 'failed')",
            name="target_customer_candidates_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("target_customer_discovery_runs.id"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    industry: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    buyer_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    source_channel: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    match_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    added_lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"), nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default="pending_review", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
