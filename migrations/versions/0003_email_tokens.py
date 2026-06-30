"""email verification tokens

Revision ID: 0003_email_tokens
Revises: 0002_account_models
Create Date: 2026-06-17 05:18:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_email_tokens"
down_revision: str | None = "0002_account_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_tokens",
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_type", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "token_type in ('verify', 'reset')", name=op.f("ck_email_tokens_email_token_type")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_email_tokens_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("token", name=op.f("pk_email_tokens")),
    )
    op.create_index(op.f("ix_email_tokens_email"), "email_tokens", ["email"], unique=False)
    op.create_index(op.f("ix_email_tokens_tenant_id"), "email_tokens", ["tenant_id"], unique=False)
    op.create_index(
        op.f("ix_email_tokens_token_type"), "email_tokens", ["token_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_email_tokens_token_type"), table_name="email_tokens")
    op.drop_index(op.f("ix_email_tokens_tenant_id"), table_name="email_tokens")
    op.drop_index(op.f("ix_email_tokens_email"), table_name="email_tokens")
    op.drop_table("email_tokens")
