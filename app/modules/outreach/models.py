"""Outreach models: EmailTemplate, OutreachMessage, EmailTracking, Suppression."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


def _hex() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_email_templates_tenant_name"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str] = mapped_column(String(10000), default="", nullable=False)
    body_html: Mapped[str] = mapped_column(String(20000), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class OutreachMessage(Base):
    __tablename__ = "outreach_messages"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','sent','failed','suppressed')", name="outreach_msg_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    template_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_text: Mapped[str] = mapped_column(String(10000), default="", nullable=False)
    body_html: Mapped[str] = mapped_column(String(20000), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    provider: Mapped[str] = mapped_column(String(24), default="fake", nullable=False)
    provider_message_id: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    error_code: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class EmailTracking(Base):
    __tablename__ = "email_tracking"

    tracking_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), nullable=False, index=True)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("outreach_messages.id"), nullable=False, index=True
    )
    subject: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    target_url: Mapped[str] = mapped_column(String(2000), default="", nullable=False)
    open_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    click_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class Suppression(Base):
    __tablename__ = "suppressions"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_suppressions_tenant_email"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    reason: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
