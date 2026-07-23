"""idempotency lease fields: claim_token, processing_expires_at

Revision ID: 0012_idempotency_lease
Revises: 0011_security_hardening
Create Date: 2026-07-22 23:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_idempotency_lease"
down_revision: str | None = "0011_security_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_exists(table: str, column: str) -> bool:
    """Check if a column already exists (compat with modified 0011)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # Add claim_token if not already present (compat with modified 0011)
    if not _column_exists("inbound_idempotency", "claim_token"):
        with op.batch_alter_table("inbound_idempotency") as batch_op:
            batch_op.add_column(
                sa.Column("claim_token", sa.String(64), nullable=False, server_default="")
            )

    # Add processing_expires_at if not already present
    if not _column_exists("inbound_idempotency", "processing_expires_at"):
        with op.batch_alter_table("inbound_idempotency") as batch_op:
            batch_op.add_column(
                sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=True)
            )

    # Backfill: set expired lease for any historical 'processing' records with NULL lease
    # This allows them to be taken over by new requests
    op.execute(
        "UPDATE inbound_idempotency"
        " SET processing_expires_at = '2020-01-01 00:00:00'"
        " WHERE status = 'processing' AND processing_expires_at IS NULL"
    )


def downgrade() -> None:
    with op.batch_alter_table("inbound_idempotency") as batch_op:
        batch_op.drop_column("processing_expires_at")
        batch_op.drop_column("claim_token")
