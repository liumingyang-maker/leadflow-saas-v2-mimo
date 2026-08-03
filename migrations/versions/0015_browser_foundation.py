"""add disabled browser research foundation

Revision ID: 0015_browser_foundation
Revises: 0014_acquisition_core
Create Date: 2026-08-03 21:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_browser_foundation"
down_revision: str | None = "0014_acquisition_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "browser_site_policies",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("access_mode", sa.String(24), nullable=False, server_default="review_required"),
        sa.Column("terms_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("robots_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("allowed_origins_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("allowed_paths_json", sa.Text(), nullable=False, server_default='["/"]'),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("max_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("action_delay_seconds", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("approved_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "access_mode in ('auto_public','review_required','manual_only','blocked')",
            name="browser_site_policy_access_mode",
        ),
        sa.CheckConstraint(
            "terms_status in ('unknown','approved','rejected')",
            name="browser_site_policy_terms_status",
        ),
        sa.CheckConstraint(
            "robots_status in ('unknown','allowed','disallowed')",
            name="browser_site_policy_robots_status",
        ),
        sa.CheckConstraint("max_pages between 1 and 25", name="browser_site_policy_max_pages"),
        sa.CheckConstraint(
            "max_seconds between 10 and 300", name="browser_site_policy_max_seconds"
        ),
        sa.CheckConstraint(
            "action_delay_seconds between 0 and 60",
            name="browser_site_policy_action_delay",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_browser_site_policies"),
        sa.UniqueConstraint("tenant_id", "canonical_domain", name="uq_browser_site_policy_domain"),
    )
    op.create_index("ix_browser_site_policies_tenant_id", "browser_site_policies", ["tenant_id"])
    op.create_index(
        "ix_browser_site_policies_access_mode", "browser_site_policies", ["access_mode"]
    )

    op.create_table(
        "browser_research_runs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("owner_type", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.String(64), nullable=False),
        sa.Column("site_policy_id", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("requested_url", sa.String(1000), nullable=False),
        sa.Column("final_url", sa.String(1000), nullable=False, server_default=""),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("policy_decision_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("plan_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("budget_json", sa.Text(), nullable=False),
        sa.Column("descriptor_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("run_token_digest", sa.String(64), nullable=False),
        sa.Column("transport_job_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_call_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bytes_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("artifact_manifest_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("error_summary", sa.String(500), nullable=False, server_default=""),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "owner_type in ('radar_run','acquisition_candidate','smoke')",
            name="browser_run_owner_type",
        ),
        sa.CheckConstraint(
            "status in ('queued','running','completed','partial','blocked','failed','cancelled')",
            name="browser_run_status",
        ),
        sa.CheckConstraint("attempt >= 0", name="browser_run_attempt"),
        sa.CheckConstraint("page_count between 0 and 25", name="browser_run_page_count"),
        sa.CheckConstraint("tool_call_count between 0 and 30", name="browser_run_tool_call_count"),
        sa.CheckConstraint("bytes_written >= 0", name="browser_run_bytes_written"),
        sa.CheckConstraint("length(run_token_digest) = 64", name="browser_run_token_digest_length"),
        sa.CheckConstraint("length(result_json) <= 100000", name="browser_run_result_json_length"),
        sa.ForeignKeyConstraint(
            ["site_policy_id"],
            ["browser_site_policies.id"],
            name="fk_browser_research_runs_site_policy_id_browser_site_policies",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_browser_research_runs"),
    )
    for column in (
        "tenant_id",
        "owner_type",
        "owner_id",
        "site_policy_id",
        "status",
        "canonical_domain",
    ):
        op.create_index(f"ix_browser_research_runs_{column}", "browser_research_runs", [column])


def downgrade() -> None:
    for column in (
        "canonical_domain",
        "status",
        "site_policy_id",
        "owner_id",
        "owner_type",
        "tenant_id",
    ):
        op.drop_index(f"ix_browser_research_runs_{column}", table_name="browser_research_runs")
    op.drop_table("browser_research_runs")
    op.drop_index("ix_browser_site_policies_access_mode", table_name="browser_site_policies")
    op.drop_index("ix_browser_site_policies_tenant_id", table_name="browser_site_policies")
    op.drop_table("browser_site_policies")
