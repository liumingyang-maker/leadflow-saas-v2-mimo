"""tenant product profiles

Revision ID: 0012_tenant_product_profiles
Revises: 0011_ai_control_plane
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_tenant_product_profiles"
down_revision: str | None = "0011_ai_control_plane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_product_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("raw_company_intro", sa.Text(), nullable=False),
        sa.Column("raw_products", sa.Text(), nullable=False),
        sa.Column("raw_website_url", sa.Text(), nullable=False),
        sa.Column("raw_target_markets", sa.Text(), nullable=False),
        sa.Column("raw_advantages", sa.Text(), nullable=False),
        sa.Column("raw_certificates", sa.Text(), nullable=False),
        sa.Column("raw_moq", sa.Text(), nullable=False),
        sa.Column("raw_delivery_capacity", sa.Text(), nullable=False),
        sa.Column("raw_customer_countries", sa.Text(), nullable=False),
        sa.Column("extracted_profile_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("last_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('draft', 'extracted', 'confirmed', 'failed')",
            name=op.f("ck_tenant_product_profiles_tenant_product_profiles_status"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_tenant_product_profiles_tenant_id_tenants")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenant_product_profiles")),
        sa.UniqueConstraint("tenant_id", name=op.f("uq_tenant_product_profiles_tenant_id")),
    )
    op.create_index(
        op.f("ix_tenant_product_profiles_status"),
        "tenant_product_profiles",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tenant_product_profiles_tenant_id"),
        "tenant_product_profiles",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_tenant_product_profiles_tenant_id"), table_name="tenant_product_profiles"
    )
    op.drop_index(op.f("ix_tenant_product_profiles_status"), table_name="tenant_product_profiles")
    op.drop_table("tenant_product_profiles")
