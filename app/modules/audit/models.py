"""Audit event model for security and operational events."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base


def _hex() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True, default="")
    actor_user_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    actor_admin_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    actor_type: Mapped[str] = mapped_column(String(24), default="user", nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    ip_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    safe_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        CheckConstraint("actor_type in ('user','admin','system')", name="audit_actor_type"),
    )
