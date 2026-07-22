"""tenant secrets (encrypted)

Revision ID: 0004_tenant_secrets
Revises: 0003_email_tokens
Create Date: 2026-06-17 06:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_tenant_secrets"
down_revision: str | None = "0003_email_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_secrets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_secrets_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_secrets")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_secrets_tenant_name"),
    )
    op.create_index(
        op.f("ix_tenant_secrets_tenant_id"), "tenant_secrets", ["tenant_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_tenant_secrets_tenant_id"), table_name="tenant_secrets")
    op.drop_table("tenant_secrets")
