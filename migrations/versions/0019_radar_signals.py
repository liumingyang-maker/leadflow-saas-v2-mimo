"""add drift-protected radar change signals

Revision ID: 0019_radar_signals
Revises: 0018_radar_relationships
Create Date: 2026-08-04 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_radar_signals"
down_revision: str | None = "0018_radar_relationships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_change_signals",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("previous_snapshot_id", sa.String(64), nullable=True),
        sa.Column("current_snapshot_id", sa.String(64), nullable=False),
        sa.Column("change_type", sa.String(24), nullable=False),
        sa.Column("materiality", sa.String(24), nullable=False, server_default="informational"),
        sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reason_codes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(24), nullable=False, server_default="open"),
        sa.Column("detector_version", sa.String(40), nullable=False),
        sa.Column("classifier_version", sa.String(40), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("decided_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "change_type in ("
            "'product','market','dealer_added','dealer_removed',"
            "'partnership','contact','other')",
            name="radar_signal_change_type",
        ),
        sa.CheckConstraint(
            "materiality in ('material','informational','noise')",
            name="radar_signal_materiality",
        ),
        sa.CheckConstraint(
            "status in ('open','acknowledged','dismissed')",
            name="radar_signal_status",
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["competitor_profiles.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["radar_runs.id"]),
        sa.ForeignKeyConstraint(["previous_snapshot_id"], ["radar_snapshots.id"]),
        sa.ForeignKeyConstraint(["current_snapshot_id"], ["radar_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "profile_id",
            "run_id",
            "current_snapshot_id",
            name="uq_radar_signal_run_snapshot",
        ),
    )
    for column in (
        "tenant_id",
        "profile_id",
        "run_id",
        "previous_snapshot_id",
        "current_snapshot_id",
        "status",
    ):
        op.create_index(f"ix_radar_change_signals_{column}", "radar_change_signals", [column])


def downgrade() -> None:
    for column in (
        "status",
        "current_snapshot_id",
        "previous_snapshot_id",
        "run_id",
        "profile_id",
        "tenant_id",
    ):
        op.drop_index(f"ix_radar_change_signals_{column}", table_name="radar_change_signals")
    op.drop_table("radar_change_signals")
