from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class RadarCompetitorSuggestion(Base):
    """A cited proposal awaiting an explicit human decision."""

    __tablename__ = "radar_competitor_suggestions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "mission_id",
            "canonical_domain",
            name="uq_radar_suggestion_mission_domain",
        ),
        CheckConstraint(
            "status in ('proposed','approved','dismissed')",
            name="radar_suggestion_status",
        ),
        CheckConstraint(
            "length(evidence_hash) = 64",
            name="radar_suggestion_evidence_hash_length",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_missions.id"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    official_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False, index=True)
    decided_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class CompetitorProfile(Base):
    """A tenant-owned competitor approved for future manual tracking."""

    __tablename__ = "competitor_profiles"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "mission_id",
            "canonical_domain",
            name="uq_competitor_profile_mission_domain",
        ),
        CheckConstraint(
            "status in ('active','paused','archived')",
            name="competitor_profile_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_missions.id"), nullable=False, index=True
    )
    product_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("product_knowledge_snapshots.id"), nullable=False, index=True
    )
    source_suggestion_id: Mapped[str | None] = mapped_column(
        ForeignKey("radar_competitor_suggestions.id"), index=True
    )
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    official_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False, index=True)
    tracking_config_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    approved_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
