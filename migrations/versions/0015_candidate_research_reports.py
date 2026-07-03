"""candidate research reports

Revision ID: 0015_candidate_research_reports
Revises: 0014_acquisition_provider_settings
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_candidate_research_reports"
down_revision: str | None = "0014_acquisition_provider_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_research_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("research_type", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("search_provider", sa.String(length=32), nullable=False),
        sa.Column("company_name", sa.String(length=300), nullable=False),
        sa.Column("company_domain", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("buyer_type", sa.String(length=120), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("why_potential_buyer", sa.Text(), nullable=False),
        sa.Column("product_fit", sa.Text(), nullable=False),
        sa.Column("possible_use_cases_json", sa.Text(), nullable=False),
        sa.Column("buyer_signals_json", sa.Text(), nullable=False),
        sa.Column("risk_signals_json", sa.Text(), nullable=False),
        sa.Column("suggested_next_action", sa.Text(), nullable=False),
        sa.Column("suggested_outreach_angle", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("ai_model", sa.String(length=120), nullable=False),
        sa.Column("ai_usage_ledger_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('pending', 'completed', 'failed')",
            name=op.f("ck_candidate_research_reports_candidate_research_reports_status"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_usage_ledger_id"],
            ["ai_usage_ledger.id"],
            name=op.f("fk_candidate_research_reports_ai_usage_ledger_id_ai_usage_ledger"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["target_customer_candidates.id"],
            name=op.f("fk_candidate_research_reports_candidate_id_target_customer_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_candidate_research_reports_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_research_reports")),
    )
    op.create_index(
        op.f("ix_candidate_research_reports_candidate_id"),
        "candidate_research_reports",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_research_reports_created_at"),
        "candidate_research_reports",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_research_reports_status"),
        "candidate_research_reports",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_research_reports_tenant_id"),
        "candidate_research_reports",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_candidate_research_reports_tenant_id"),
        table_name="candidate_research_reports",
    )
    op.drop_index(
        op.f("ix_candidate_research_reports_status"),
        table_name="candidate_research_reports",
    )
    op.drop_index(
        op.f("ix_candidate_research_reports_created_at"),
        table_name="candidate_research_reports",
    )
    op.drop_index(
        op.f("ix_candidate_research_reports_candidate_id"),
        table_name="candidate_research_reports",
    )
    op.drop_table("candidate_research_reports")
