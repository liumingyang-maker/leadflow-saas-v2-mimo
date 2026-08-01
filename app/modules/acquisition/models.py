from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
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


class ProductKnowledgeSnapshot(Base):
    __tablename__ = "product_knowledge_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "product_name",
            "version",
            name="uq_product_snapshot_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_revision: Mapped[str] = mapped_column(String(100), default="manual", nullable=False)
    facts_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    prohibited_claims_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(36), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class AcquisitionMission(Base):
    __tablename__ = "acquisition_missions"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','queued','running','paused','completed','failed','cancelled')",
            name="acquisition_mission_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False, index=True)
    product_snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("product_knowledge_snapshots.id"), nullable=False, index=True
    )
    target_profile_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    channel_policy_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    budget_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    automation_level: Mapped[str] = mapped_column(
        String(32), default="research_only", nullable=False
    )
    cost_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    retrospective_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_by: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AcquisitionCandidate(Base):
    __tablename__ = "acquisition_candidates"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "mission_id",
            "dedupe_key",
            name="uq_candidate_mission_dedupe",
        ),
        CheckConstraint(
            "status in ('discovered','verifying','needs_evidence','eligible',"
            "'rejected','accepted','promoted')",
            name="acquisition_candidate_status",
        ),
        CheckConstraint(
            "priority_score >= 0 and priority_score <= 100",
            name="candidate_priority_range",
        ),
        CheckConstraint(
            "signal_coverage >= 0 and signal_coverage <= 100",
            name="candidate_coverage_range",
        ),
        CheckConstraint(
            "country_resolution_status in ('unknown','confirmed','conflicting')",
            name="candidate_country_resolution_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_missions.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), default="discovered", nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(24), default="company", nullable=False)
    company_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    domain: Mapped[str] = mapped_column(String(253), default="", nullable=False, index=True)
    website: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    hq_country_code: Mapped[str] = mapped_column(String(2), default="", nullable=False)
    opportunity_country_code: Mapped[str] = mapped_column(
        String(2), default="", nullable=False, index=True
    )
    contact_country_code: Mapped[str] = mapped_column(String(2), default="", nullable=False)
    country_resolution_status: Mapped[str] = mapped_column(
        String(24), default="unknown", nullable=False
    )
    source_channel: Mapped[str] = mapped_column(String(60), default="", nullable=False, index=True)
    source_provider: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    contact_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    observed_facts_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    inferences_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    unknowns_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    eligibility_code: Mapped[str] = mapped_column(
        String(80), default="", nullable=False, index=True
    )
    priority_score: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    priority_band: Mapped[str] = mapped_column(String(16), default="", nullable=False, index=True)
    signal_coverage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_confidence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decision_reason_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    decision_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decided_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str] = mapped_column(String(500), nullable=False)
    promoted_lead_id: Mapped[str] = mapped_column(
        String(36), default="", nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class CandidateEvidence(Base):
    __tablename__ = "candidate_evidence"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "canonical_url",
            "content_hash",
            name="uq_evidence_content",
        ),
        CheckConstraint("trust_tier in ('A','B','C','D','E')", name="evidence_trust_tier"),
        CheckConstraint(
            "validation_status in ('unverified','valid','stale','unreachable','contradicted')",
            name="evidence_validation_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_candidates.id"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(String(64), default="", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    source_type: Mapped[str] = mapped_column(String(60), default="web", nullable=False)
    trust_tier: Mapped[str] = mapped_column(String(4), default="D", nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    canonical_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    excerpt: Mapped[str] = mapped_column(String(4000), default="", nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supports_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(24), default="unverified", nullable=False)


class CandidateAssessment(Base):
    __tablename__ = "candidate_assessments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "evidence_bundle_hash",
            "policy_version",
            "score_version",
            "prompt_version",
            "model_id",
            name="uq_assessment_input_version",
        ),
        CheckConstraint(
            "signal_coverage >= 0 and signal_coverage <= 100",
            name="assessment_coverage_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_candidates.id"), nullable=False, index=True
    )
    evidence_bundle_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), nullable=False)
    score_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    model_provider: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    hard_gate_json: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown_json: Mapped[str] = mapped_column(Text, nullable=False)
    signal_coverage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    priority_mode: Mapped[str] = mapped_column(String(60), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class MissionSuggestion(Base):
    __tablename__ = "mission_suggestions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_suggestion_dedupe"),
        CheckConstraint("status in ('proposed','applied','dismissed')", name="suggestion_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(
        ForeignKey("acquisition_missions.id"), nullable=False, index=True
    )
    suggestion_type: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposed_change_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)
    applied_profile_version: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_key", name="uq_notification_dedupe"),
        CheckConstraint("status in ('unread','read','archived')", name="notification_status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    target_url: Mapped[str] = mapped_column(String(500), default="/workbench", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="unread", nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderStatus(Base):
    __tablename__ = "provider_statuses"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_provider_status"),
        CheckConstraint(
            "status in ('unknown','healthy','degraded','failed')", name="provider_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="unknown", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
