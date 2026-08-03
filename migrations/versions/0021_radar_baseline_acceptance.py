"""require explicit acceptance after radar baseline drift

Revision ID: 0021_radar_baseline_acceptance
Revises: 0020_radar_active_run_guard
Create Date: 2026-08-04 01:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_radar_baseline_acceptance"
down_revision: str | None = "0020_radar_active_run_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_runs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "baseline_accepted",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
    op.get_bind().exec_driver_sql(
        "UPDATE radar_runs SET baseline_accepted = 0 "
        "WHERE result_summary_json LIKE '%\"possible_baseline_drift\":true%'"
    )


def downgrade() -> None:
    with op.batch_alter_table("radar_runs") as batch_op:
        batch_op.drop_column("baseline_accepted")
