"""acquisition provider settings

Revision ID: 0014_acquisition_provider_settings
Revises: 0013_target_customer_discovery
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_acquisition_provider_settings"
down_revision: str | None = "0013_target_customer_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "acquisition_provider_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_last4", sa.String(length=8), nullable=False),
        sa.Column("daily_spend_cap_cents", sa.Integer(), nullable=False),
        sa.Column("query_limit_per_run", sa.Integer(), nullable=False),
        sa.Column("result_limit_per_run", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=32), nullable=False),
        sa.Column("last_error_code", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider in ('disabled', 'fake', 'brave')",
            name=op.f("ck_acquisition_provider_settings_acquisition_provider_settings_provider"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acquisition_provider_settings")),
    )


def downgrade() -> None:
    op.drop_table("acquisition_provider_settings")
