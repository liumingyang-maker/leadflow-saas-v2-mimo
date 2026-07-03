from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

DISCOVERY_RUN_STATUSES = ("draft", "planned", "matched", "failed")
CANDIDATE_STATUSES = ("pending_review", "added_to_crm", "dismissed", "duplicate", "failed")
RESEARCH_REPORT_STATUSES = ("pending", "completed", "failed")
OUTREACH_DRAFT_STATUSES = ("completed", "failed")


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


class CandidateResearchReport(Base):
    __tablename__ = "candidate_research_reports"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'completed', 'failed')",
            name="candidate_research_reports_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("target_customer_candidates.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    research_type: Mapped[str] = mapped_column(
        String(40), default="ai_company_research", nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    search_provider: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    company_name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    company_domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    buyer_type: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    why_potential_buyer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    product_fit: Mapped[str] = mapped_column(Text, default="", nullable=False)
    possible_use_cases_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    buyer_signals_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    risk_signals_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    suggested_next_action: Mapped[str] = mapped_column(Text, default="", nullable=False)
    suggested_outreach_angle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    ai_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    ai_usage_ledger_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_usage_ledger.id"), nullable=True
    )
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class CandidateOutreachDraft(Base):
    __tablename__ = "candidate_outreach_drafts"
    __table_args__ = (
        CheckConstraint(
            "status in ('completed', 'failed')",
            name="candidate_outreach_drafts_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("target_customer_candidates.id"), nullable=False, index=True
    )
    research_report_id: Mapped[str | None] = mapped_column(
        ForeignKey("candidate_research_reports.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="completed", nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    ai_model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="en", nullable=False)
    tone: Mapped[str] = mapped_column(String(40), default="professional_concise", nullable=False)
    subject: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    short_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    follow_up_angle: Mapped[str] = mapped_column(Text, default="", nullable=False)
    personalization_notes_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    confidence_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    disclaimer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_usage_ledger_id: Mapped[str | None] = mapped_column(
        ForeignKey("ai_usage_ledger.id"), nullable=True
    )
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
