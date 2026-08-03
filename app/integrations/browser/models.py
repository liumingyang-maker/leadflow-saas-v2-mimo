from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit, urlunsplit

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


def redact_url_query(value: str) -> str:
    """Preserve the site/page identity without retaining query-string data."""

    try:
        parsed = urlsplit(value)
    except (TypeError, ValueError):
        return ""
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


class BrowserSitePolicy(Base):
    __tablename__ = "browser_site_policies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "canonical_domain", name="uq_browser_site_policy_domain"),
        CheckConstraint(
            "access_mode in ('auto_public','review_required','manual_only','blocked')",
            name="browser_site_policy_access_mode",
        ),
        CheckConstraint(
            "terms_status in ('unknown','approved','rejected')",
            name="browser_site_policy_terms_status",
        ),
        CheckConstraint(
            "robots_status in ('unknown','allowed','disallowed')",
            name="browser_site_policy_robots_status",
        ),
        CheckConstraint("max_pages between 1 and 25", name="browser_site_policy_max_pages"),
        CheckConstraint("max_seconds between 10 and 300", name="browser_site_policy_max_seconds"),
        CheckConstraint(
            "action_delay_seconds between 0 and 60",
            name="browser_site_policy_action_delay",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False)
    access_mode: Mapped[str] = mapped_column(
        String(24), default="review_required", nullable=False, index=True
    )
    terms_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    robots_status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    allowed_origins_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    allowed_paths_json: Mapped[str] = mapped_column(Text, default='["/"]', nullable=False)
    max_pages: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    max_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    action_delay_seconds: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_by: Mapped[str] = mapped_column(String(36), default="", nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class BrowserResearchRun(Base):
    __tablename__ = "browser_research_runs"
    __table_args__ = (
        CheckConstraint(
            "owner_type in ('radar_run','acquisition_candidate','smoke')",
            name="browser_run_owner_type",
        ),
        CheckConstraint(
            "status in ('queued','running','completed','partial','blocked','failed','cancelled')",
            name="browser_run_status",
        ),
        CheckConstraint("attempt >= 0", name="browser_run_attempt"),
        CheckConstraint("page_count between 0 and 25", name="browser_run_page_count"),
        CheckConstraint("tool_call_count between 0 and 30", name="browser_run_tool_call_count"),
        CheckConstraint("bytes_written >= 0", name="browser_run_bytes_written"),
        CheckConstraint("length(run_token_digest) = 64", name="browser_run_token_digest_length"),
        CheckConstraint("length(result_json) <= 100000", name="browser_run_result_json_length"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_id)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    site_policy_id: Mapped[str | None] = mapped_column(
        ForeignKey("browser_site_policies.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", nullable=False, index=True)
    requested_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    final_url: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    canonical_domain: Mapped[str] = mapped_column(String(253), nullable=False, index=True)
    policy_decision_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    budget_json: Mapped[str] = mapped_column(Text, nullable=False)
    descriptor_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    run_token_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    transport_job_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tool_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bytes_written: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    artifact_manifest_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    error_summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    def __init__(self, **kwargs) -> None:
        for field in ("requested_url", "final_url"):
            if field in kwargs:
                kwargs[field] = redact_url_query(str(kwargs[field]))
        super().__init__(**kwargs)
