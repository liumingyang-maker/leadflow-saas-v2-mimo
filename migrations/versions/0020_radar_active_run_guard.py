"""guard one active manual Radar run per profile

Revision ID: 0020_radar_active_run_guard
Revises: 0019_radar_signals
Create Date: 2026-08-04 01:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_radar_active_run_guard"
down_revision: str | None = "0019_radar_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_runs") as batch_op:
        batch_op.add_column(sa.Column("active_key", sa.String(16), nullable=True))
    op.execute(
        "WITH ranked AS ("
        " SELECT id, ROW_NUMBER() OVER ("
        " PARTITION BY tenant_id, profile_id ORDER BY created_at DESC, id DESC"
        " ) AS position"
        " FROM radar_runs WHERE status IN ('queued', 'running')"
        ")"
        " UPDATE radar_runs"
        " SET active_key = 'active'"
        " WHERE id IN (SELECT id FROM ranked WHERE position = 1)"
    )
    op.execute(
        "UPDATE radar_runs"
        " SET status = 'failed', stage = 'migration_superseded',"
        " finished_at = CURRENT_TIMESTAMP,"
        ' result_summary_json = \'{"reason_codes":["migration_superseded"]}\''
        " WHERE status IN ('queued', 'running') AND active_key IS NULL"
    )
    with op.batch_alter_table("radar_runs") as batch_op:
        batch_op.create_unique_constraint(
            "uq_radar_run_profile_active",
            ["tenant_id", "profile_id", "active_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("radar_runs") as batch_op:
        batch_op.drop_constraint("uq_radar_run_profile_active", type_="unique")
        batch_op.drop_column("active_key")
