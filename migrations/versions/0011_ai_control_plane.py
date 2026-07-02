"""ai control plane

Revision ID: 0011_ai_control_plane
Revises: 0010_audit_events
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_ai_control_plane"
down_revision: str | None = "0010_audit_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("api_key_encrypted", sa.Text(), nullable=False),
        sa.Column("api_key_last4", sa.String(length=8), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider in ('disabled', 'fake', 'openai_compatible')",
            name=op.f("ck_ai_provider_settings_ai_provider_settings_provider"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_provider_settings")),
    )
    op.create_table(
        "tenant_ai_quotas",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("plan_name", sa.String(length=24), nullable=False),
        sa.Column("monthly_included_credits", sa.Integer(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_ai_quotas_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_ai_quotas")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_tenant_ai_quotas_tenant_id")),
    )
    op.create_index(
        op.f("ix_tenant_ai_quotas_tenant_id"), "tenant_ai_quotas", ["tenant_id"], unique=False
    )
    op.create_table(
        "ai_usage_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("feature_name", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("credits_charged", sa.Integer(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('success', 'failed', 'blocked_quota', 'disabled')",
            name=op.f("ck_ai_usage_ledger_ai_usage_ledger_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_ai_usage_ledger_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_ledger")),
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_created_at"), "ai_usage_ledger", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_feature_name"),
        "ai_usage_ledger",
        ["feature_name"],
        unique=False,
    )
    op.create_index(op.f("ix_ai_usage_ledger_status"), "ai_usage_ledger", ["status"], unique=False)
    op.create_index(
        op.f("ix_ai_usage_ledger_tenant_id"), "ai_usage_ledger", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_ai_usage_ledger_user_id"), "ai_usage_ledger", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_usage_ledger_user_id"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_tenant_id"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_status"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_feature_name"), table_name="ai_usage_ledger")
    op.drop_index(op.f("ix_ai_usage_ledger_created_at"), table_name="ai_usage_ledger")
    op.drop_table("ai_usage_ledger")
    op.drop_index(op.f("ix_tenant_ai_quotas_tenant_id"), table_name="tenant_ai_quotas")
    op.drop_table("tenant_ai_quotas")
    op.drop_table("ai_provider_settings")
