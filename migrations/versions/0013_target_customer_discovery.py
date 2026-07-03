"""target customer discovery

Revision ID: 0013_target_customer_discovery
Revises: 0012_tenant_product_profiles
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_target_customer_discovery"
down_revision: str | None = "0012_tenant_product_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "target_customer_discovery_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("product_profile_id", sa.String(length=36), nullable=False),
        sa.Column("filters_json", sa.Text(), nullable=False),
        sa.Column("generated_plan_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("generated_count", sa.Integer(), nullable=False),
        sa.Column("credits_estimated", sa.Integer(), nullable=False),
        sa.Column("credits_charged", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('draft', 'planned', 'matched', 'failed')",
            name=op.f("ck_target_customer_discovery_runs_target_customer_discovery_runs_status"),
        ),
        sa.ForeignKeyConstraint(
            ["product_profile_id"],
            ["tenant_product_profiles.id"],
            name=op.f(
                "fk_target_customer_discovery_runs_product_profile_id_tenant_product_profiles"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_target_customer_discovery_runs_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_target_customer_discovery_runs")),
    )
    op.create_index(
        op.f("ix_target_customer_discovery_runs_created_at"),
        "target_customer_discovery_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_customer_discovery_runs_product_profile_id"),
        "target_customer_discovery_runs",
        ["product_profile_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_customer_discovery_runs_status"),
        "target_customer_discovery_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_customer_discovery_runs_tenant_id"),
        "target_customer_discovery_runs",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "target_customer_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("company_name", sa.String(length=300), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("buyer_type", sa.String(length=120), nullable=False),
        sa.Column("source_channel", sa.String(length=80), nullable=False),
        sa.Column("match_reason", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("raw_data_json", sa.Text(), nullable=False),
        sa.Column("added_lead_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending_review', 'added_to_crm', 'dismissed', 'duplicate', 'failed')",
            name=op.f("ck_target_customer_candidates_target_customer_candidates_status"),
        ),
        sa.ForeignKeyConstraint(
            ["added_lead_id"],
            ["leads.id"],
            name=op.f("fk_target_customer_candidates_added_lead_id_leads"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["target_customer_discovery_runs.id"],
            name=op.f("fk_target_customer_candidates_run_id_target_customer_discovery_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_target_customer_candidates_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_target_customer_candidates")),
    )
    op.create_index(
        op.f("ix_target_customer_candidates_run_id"),
        "target_customer_candidates",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_customer_candidates_status"),
        "target_customer_candidates",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_target_customer_candidates_tenant_id"),
        "target_customer_candidates",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_target_customer_candidates_tenant_id"),
        table_name="target_customer_candidates",
    )
    op.drop_index(
        op.f("ix_target_customer_candidates_status"),
        table_name="target_customer_candidates",
    )
    op.drop_index(
        op.f("ix_target_customer_candidates_run_id"),
        table_name="target_customer_candidates",
    )
    op.drop_table("target_customer_candidates")
    op.drop_index(
        op.f("ix_target_customer_discovery_runs_tenant_id"),
        table_name="target_customer_discovery_runs",
    )
    op.drop_index(
        op.f("ix_target_customer_discovery_runs_status"),
        table_name="target_customer_discovery_runs",
    )
    op.drop_index(
        op.f("ix_target_customer_discovery_runs_product_profile_id"),
        table_name="target_customer_discovery_runs",
    )
    op.drop_index(
        op.f("ix_target_customer_discovery_runs_created_at"),
        table_name="target_customer_discovery_runs",
    )
    op.drop_table("target_customer_discovery_runs")
