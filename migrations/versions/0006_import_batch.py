"""import batch table for server-side preview persistence

Revision ID: 0006_import_batch
Revises: 0005_lead_crm_models
Create Date: 2026-06-17 08:15:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_import_batch"
down_revision: str | None = "0005_lead_crm_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=False),
        sa.Column("valid_rows", sa.Integer(), nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), nullable=False),
        sa.Column("invalid_rows", sa.Integer(), nullable=False),
        sa.Column("errors_json", sa.Text(), nullable=False),
        sa.Column("unmapped_columns", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(
        op.f("ix_import_batches_tenant_id"), "import_batches", ["tenant_id"], unique=False
    )
    op.create_index(op.f("ix_import_batches_status"), "import_batches", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_import_batches_status"), table_name="import_batches")
    op.drop_index(op.f("ix_import_batches_tenant_id"), table_name="import_batches")
    op.drop_table("import_batches")
