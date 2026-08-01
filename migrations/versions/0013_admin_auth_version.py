"""add auth_version to admin_users

Revision ID: 0013_admin_auth_version
Revises: 0012_idempotency_lease
Create Date: 2026-08-01 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_admin_auth_version"
down_revision: str | None = "0012_idempotency_lease"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    with op.batch_alter_table("admin_users") as batch_op:
        batch_op.drop_column("auth_version")
