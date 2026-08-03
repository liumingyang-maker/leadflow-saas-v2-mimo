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


class RadarRun(Base):
    """One explicitly requested, manually initiated Radar scan."""

    __tablename__ = "radar_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','running','succeeded','partial','failed','cancelled')",
            name="radar_run_status",
        ),
        CheckConstraint("length(budget_json) <= 5000", name="radar_run_budget_size"),
        CheckConstraint("length(result_summary_json) <= 20000", name="radar_run_summary_size"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    root_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), default="queued", nullable=False)
    budget_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    parser_version: Mapped[str] = mapped_column(
        String(40), default="radar-static-v1", nullable=False
    )
    diff_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RadarSnapshot(Base):
    """Immutable, sanitized structured observation from a Radar Run."""

    __tablename__ = "radar_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "profile_id",
            "canonical_url",
            "content_hash",
            name="uq_radar_snapshot_profile_url_hash",
        ),
        CheckConstraint(
            "page_kind in ('home','product','dealers','partners','contact','about','other')",
            name="radar_snapshot_page_kind",
        ),
        CheckConstraint(
            "source_method in ('static','browser')", name="radar_snapshot_source_method"
        ),
        CheckConstraint(
            "validation_status in ('valid','partial','rejected','unreachable')",
            name="radar_snapshot_validation_status",
        ),
        CheckConstraint("length(excerpt) <= 4000", name="radar_snapshot_excerpt_size"),
        CheckConstraint("length(facts_json) <= 50000", name="radar_snapshot_facts_size"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("radar_runs.id"), nullable=False, index=True)
    page_kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    requested_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    facts_json: Mapped[str] = mapped_column(Text, nullable=False)
    excerpt: Mapped[str] = mapped_column(String(4000), default="", nullable=False)
    source_method: Mapped[str] = mapped_column(String(24), default="static", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(24), default="valid", nullable=False)
    extractor_version: Mapped[str] = mapped_column(
        String(40), default="radar-static-v1", nullable=False
    )
    artifact_ref: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
