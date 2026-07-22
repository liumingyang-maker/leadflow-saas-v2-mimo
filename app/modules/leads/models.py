from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Association table for Lead <-> Tag many-to-many
# ---------------------------------------------------------------------------


class LeadTagAssociation(Base):
    __tablename__ = "lead_tags"
    __table_args__ = (UniqueConstraint("lead_id", "tag_id", name="uq_lead_tags_lead_tag"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    tag_id: Mapped[str] = mapped_column(ForeignKey("tags.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("tenant_id", "domain", name="uq_companies_tenant_domain"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    domain: Mapped[str] = mapped_column(String(253), default="", nullable=False, index=True)
    industry: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    size: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    revenue_range: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    leads: Mapped[list[Lead]] = relationship(back_populates="company", cascade="all, delete-orphan")


# ---------------------------------------------------------------------------
# Tag
# ---------------------------------------------------------------------------


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    color: Mapped[str] = mapped_column(String(7), default="#246BFD", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


# ---------------------------------------------------------------------------
# Lead
# ---------------------------------------------------------------------------


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "status in ('raw', 'pending_review', 'accepted', 'rejected', 'duplicate')",
            name="lead_status",
        ),
        CheckConstraint(
            "stage in ('new', 'contacted', 'qualified', 'proposal', 'negotiation', 'won', 'lost')",
            name="lead_stage",
        ),
        CheckConstraint(
            "source in ('manual', 'import', 'collection', 'inbound', 'api')",
            name="lead_source",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True
    )

    email: Mapped[str] = mapped_column(String(320), default="", nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    website: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    linkedin_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    industry: Mapped[str] = mapped_column(String(120), default="", nullable=False)

    source: Mapped[str] = mapped_column(String(24), default="manual", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="raw", nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(24), default="new", nullable=False, index=True)
    confidence_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    import_batch_id: Mapped[str] = mapped_column(String(36), default="", nullable=False, index=True)
    duplicate_reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # Relationships
    company: Mapped[Company | None] = relationship(back_populates="leads")
    activities: Mapped[list[Activity]] = relationship(
        back_populates="lead", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# Activity
# ---------------------------------------------------------------------------


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        CheckConstraint(
            "action in ('created','imported','reviewed','accepted','rejected','stage_changed',"
            "'note_added','tagged','untagged','follow_up_set','contacted','emailed','called',"
            "'meeting','bulk_action','merged','other','email_sent','email_suppressed',"
            "'email_opened','email_clicked','unsubscribed','inbound_received')",
            name="activity_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    old_value: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    new_value: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    performed_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    lead: Mapped[Lead] = relationship(back_populates="activities")


# ---------------------------------------------------------------------------
# ImportBatch
# ---------------------------------------------------------------------------


class ImportBatch(Base):
    """Server-side persisted preview of an import file.

    Created during preview, consumed and marked completed during confirm.
    Expires after 1 hour.  Tenant-scoped so cross-tenant access is impossible.
    """

    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="preview", nullable=False, index=True)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    invalid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    unmapped_columns: Mapped[str] = mapped_column(Text, default="", nullable=False)
    rows_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
