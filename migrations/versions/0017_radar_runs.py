"""add manual radar runs and structured snapshots

Revision ID: 0017_radar_runs
Revises: 0016_radar_profiles
Create Date: 2026-08-03 23:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_radar_runs"
down_revision: str | None = "0016_radar_profiles"
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
        "radar_runs",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("root_job_id", sa.String(64), nullable=False),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("stage", sa.String(80), nullable=False, server_default="queued"),
        sa.Column("budget_json", sa.Text(), nullable=False),
        sa.Column("result_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "parser_version", sa.String(40), nullable=False, server_default="radar-static-v1"
        ),
        sa.Column("diff_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("classifier_version", sa.String(40), nullable=False, server_default=""),
        _timestamp("created_at"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('queued','running','succeeded','partial','failed','cancelled')",
            name="radar_run_status",
        ),
        sa.CheckConstraint("length(budget_json) <= 5000", name="radar_run_budget_size"),
        sa.CheckConstraint("length(result_summary_json) <= 20000", name="radar_run_summary_size"),
        sa.ForeignKeyConstraint(["profile_id"], ["competitor_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("tenant_id", "profile_id", "root_job_id", "status"):
        op.create_index(f"ix_radar_runs_{column}", "radar_runs", [column])

    op.create_table(
        "radar_snapshots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("page_kind", sa.String(24), nullable=False),
        sa.Column("requested_url", sa.String(1000), nullable=False),
        sa.Column("canonical_url", sa.String(1000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("facts_json", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.String(4000), nullable=False, server_default=""),
        sa.Column("source_method", sa.String(24), nullable=False, server_default="static"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="valid"),
        sa.Column(
            "extractor_version", sa.String(40), nullable=False, server_default="radar-static-v1"
        ),
        sa.Column("artifact_ref", sa.String(128), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "page_kind in ('home','product','dealers','partners','contact','about','other')",
            name="radar_snapshot_page_kind",
        ),
        sa.CheckConstraint(
            "source_method in ('static','browser')", name="radar_snapshot_source_method"
        ),
        sa.CheckConstraint(
            "validation_status in ('valid','partial','rejected','unreachable')",
            name="radar_snapshot_validation_status",
        ),
        sa.CheckConstraint("length(excerpt) <= 4000", name="radar_snapshot_excerpt_size"),
        sa.CheckConstraint("length(facts_json) <= 50000", name="radar_snapshot_facts_size"),
        sa.ForeignKeyConstraint(["profile_id"], ["competitor_profiles.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["radar_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "profile_id",
            "canonical_url",
            "content_hash",
            name="uq_radar_snapshot_profile_url_hash",
        ),
    )
    for column in ("tenant_id", "profile_id", "run_id", "page_kind"):
        op.create_index(f"ix_radar_snapshots_{column}", "radar_snapshots", [column])

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_jobs_job_type"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_jobs_job_type"),
            "job_type in ('google_search', 'google_maps', 'csv_import', 'xlsx_import', "
            "'acquisition_plan', 'web_discovery', 'website_verify', 'candidate_assess', "
            "'candidate_promote', 'feedback_summarize', 'notification_dispatch', "
            "'acquisition_reconcile', 'radar_scan')",
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_jobs_job_type"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_jobs_job_type"),
            "job_type in ('google_search', 'google_maps', 'csv_import', 'xlsx_import', "
            "'acquisition_plan', 'web_discovery', 'website_verify', 'candidate_assess', "
            "'candidate_promote', 'feedback_summarize', 'notification_dispatch', "
            "'acquisition_reconcile')",
        )
    for column in ("page_kind", "run_id", "profile_id", "tenant_id"):
        op.drop_index(f"ix_radar_snapshots_{column}", table_name="radar_snapshots")
    op.drop_table("radar_snapshots")
    for column in ("status", "root_job_id", "profile_id", "tenant_id"):
        op.drop_index(f"ix_radar_runs_{column}", table_name="radar_runs")
    op.drop_table("radar_runs")
