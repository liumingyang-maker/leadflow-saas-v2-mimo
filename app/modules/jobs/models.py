"""Persistent, tenant-scoped background job model."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import Base

VALID_STATUSES = ("queued", "running", "retrying", "succeeded", "failed", "cancelled")
VALID_JOB_TYPES = ("google_search", "google_maps", "csv_import", "xlsx_import")
MAX_ATTEMPTS_DEFAULT = 3


def _hex_uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_hex_uuid)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_summary_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    error_code: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=MAX_ATTEMPTS_DEFAULT, nullable=False)
    queue_name: Mapped[str] = mapped_column(String(60), default="default", nullable=False)
    rq_job_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status in ('queued', 'running', 'retrying', 'succeeded', 'failed', 'cancelled')",
            name="job_status",
        ),
        CheckConstraint(
            "job_type in ('google_search', 'google_maps', 'csv_import', 'xlsx_import')",
            name="job_type",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="job_progress_range"),
        CheckConstraint("attempt >= 1", name="job_attempt_min"),
        CheckConstraint("max_attempts >= 1", name="job_max_attempts_min"),
    )
