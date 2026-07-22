"""auth_version, payment tables, inbound unique constraints

Revision ID: 0011_security_hardening
Revises: 0010_audit_events
Create Date: 2026-07-22 22:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_security_hardening"
down_revision: str | None = "0010_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add auth_version to users table
    op.add_column(
        "users",
        sa.Column("auth_version", sa.Integer(), nullable=False, server_default="1"),
    )

    # 2. Add unique constraints and new columns to inbound tables (batch mode for SQLite)
    with op.batch_alter_table("inbound_rate_limits") as batch_op:
        batch_op.create_unique_constraint("uq_rate_limits_scope_bucket", ["scope", "bucket"])
    with op.batch_alter_table("inbound_idempotency") as batch_op:
        batch_op.add_column(
            sa.Column("claim_token", sa.String(64), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("processing_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
    with op.batch_alter_table("inbound_idempotency") as batch_op:
        batch_op.create_unique_constraint(
            "uq_idempotency_tenant_token_key",
            ["tenant_id", "token_digest", "idempotency_key"],
        )

    # 3. Create coupons table
    op.create_table(
        "coupons",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("discount_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_coupons"),
        sa.UniqueConstraint("code", name="uq_coupons_code"),
    )
    op.create_index("ix_coupons_code", "coupons", ["code"])

    # 4. Create payments table
    op.create_table(
        "payments",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="stripe"),
        sa.Column("provider_payment_id", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("plan", sa.String(32), nullable=False, server_default="pro"),
        sa.Column("coupon_id", sa.String(64), nullable=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_id"),
    )
    op.create_index("ix_payments_tenant_id", "payments", ["tenant_id"])

    # 5. Create payment_events table
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payment_id", sa.String(64), nullable=True),
        sa.Column("tenant_id", sa.String(36), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_payment_events"),
        sa.UniqueConstraint("provider", "event_id", name="uq_payment_events_provider_event"),
    )
    op.create_index("ix_payment_events_payment_id", "payment_events", ["payment_id"])
    op.create_index("ix_payment_events_tenant_id", "payment_events", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("payment_events")
    op.drop_table("payments")
    op.drop_table("coupons")
    with op.batch_alter_table("inbound_idempotency") as batch_op:
        batch_op.drop_constraint("uq_idempotency_tenant_token_key")
        batch_op.drop_column("processing_expires_at")
        batch_op.drop_column("claim_token")
    with op.batch_alter_table("inbound_rate_limits") as batch_op:
        batch_op.drop_constraint("uq_rate_limits_scope_bucket")
    op.drop_column("users", "auth_version")
