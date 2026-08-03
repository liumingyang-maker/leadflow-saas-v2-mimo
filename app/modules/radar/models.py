from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
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
        UniqueConstraint(
            "tenant_id",
            "profile_id",
            "active_key",
            name="uq_radar_run_profile_active",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    root_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    requested_by: Mapped[str] = mapped_column(String(36), nullable=False)
    # NULL terminal Runs do not participate in the unique key; queued/running use "active".
    active_key: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(80), default="queued", nullable=False)
    budget_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    baseline_accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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


class RadarRelationship(Base):
    """A cited company relationship observed on an approved competitor website."""

    __tablename__ = "radar_relationships"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "profile_id",
            "canonical_domain",
            "relationship_type",
            name="uq_radar_relationship_profile_domain_type",
        ),
        CheckConstraint(
            "relationship_type in ('dealer','distributor','partner','service_network','unknown')",
            name="radar_relationship_type",
        ),
        CheckConstraint(
            "evidence_strength in ('confirmed','likely','unknown')",
            name="radar_relationship_strength",
        ),
        CheckConstraint(
            "status in ('proposed','converted','dismissed')", name="radar_relationship_status"
        ),
        CheckConstraint("length(evidence_json) <= 20000", name="radar_relationship_evidence_size"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("radar_runs.id"), nullable=False, index=True)
    source_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("radar_snapshots.id"), nullable=False, index=True
    )
    company_name: Mapped[str] = mapped_column(String(300), nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    official_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    evidence_strength: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    decided_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class RadarChangeSignal(Base):
    __tablename__ = "radar_change_signals"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "profile_id",
            "run_id",
            "current_snapshot_id",
            name="uq_radar_signal_run_snapshot",
        ),
        CheckConstraint(
            "change_type in ("
            "'product','market','dealer_added','dealer_removed',"
            "'partnership','contact','other')",
            name="radar_signal_change_type",
        ),
        CheckConstraint(
            "materiality in ('material','informational','noise')",
            name="radar_signal_materiality",
        ),
        CheckConstraint(
            "status in ('open','acknowledged','dismissed')", name="radar_signal_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("competitor_profiles.id"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("radar_runs.id"), nullable=False, index=True)
    previous_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("radar_snapshots.id"), index=True
    )
    current_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("radar_snapshots.id"), nullable=False, index=True
    )
    change_type: Mapped[str] = mapped_column(String(24), nullable=False)
    materiality: Mapped[str] = mapped_column(String(24), default="informational", nullable=False)
    before_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    after_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False, index=True)
    detector_version: Mapped[str] = mapped_column(String(40), nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    decided_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
