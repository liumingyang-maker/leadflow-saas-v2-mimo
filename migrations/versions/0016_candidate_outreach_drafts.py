"""candidate outreach drafts

Revision ID: 0016_candidate_outreach_drafts
Revises: 0015_candidate_research_reports
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_candidate_outreach_drafts"
down_revision: str | None = "0015_candidate_research_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_outreach_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("research_report_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("ai_model", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("tone", sa.String(length=40), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("short_body", sa.Text(), nullable=False),
        sa.Column("follow_up_angle", sa.Text(), nullable=False),
        sa.Column("personalization_notes_json", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("confidence_note", sa.Text(), nullable=False),
        sa.Column("disclaimer", sa.Text(), nullable=False),
        sa.Column("ai_usage_ledger_id", sa.String(length=36), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('completed', 'failed')",
            name=op.f("ck_candidate_outreach_drafts_candidate_outreach_drafts_status"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_usage_ledger_id"],
            ["ai_usage_ledger.id"],
            name=op.f("fk_candidate_outreach_drafts_ai_usage_ledger_id_ai_usage_ledger"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["target_customer_candidates.id"],
            name=op.f("fk_candidate_outreach_drafts_candidate_id_target_customer_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["research_report_id"],
            ["candidate_research_reports.id"],
            name=op.f("fk_candidate_outreach_drafts_research_report_id_candidate_research_reports"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_candidate_outreach_drafts_tenant_id_tenants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_candidate_outreach_drafts")),
    )
    op.create_index(
        op.f("ix_candidate_outreach_drafts_candidate_id"),
        "candidate_outreach_drafts",
        ["candidate_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_outreach_drafts_created_at"),
        "candidate_outreach_drafts",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_outreach_drafts_research_report_id"),
        "candidate_outreach_drafts",
        ["research_report_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_outreach_drafts_status"),
        "candidate_outreach_drafts",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_candidate_outreach_drafts_tenant_id"),
        "candidate_outreach_drafts",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_candidate_outreach_drafts_tenant_id"),
        table_name="candidate_outreach_drafts",
    )
    op.drop_index(
        op.f("ix_candidate_outreach_drafts_status"),
        table_name="candidate_outreach_drafts",
    )
    op.drop_index(
        op.f("ix_candidate_outreach_drafts_research_report_id"),
        table_name="candidate_outreach_drafts",
    )
    op.drop_index(
        op.f("ix_candidate_outreach_drafts_created_at"),
        table_name="candidate_outreach_drafts",
    )
    op.drop_index(
        op.f("ix_candidate_outreach_drafts_candidate_id"),
        table_name="candidate_outreach_drafts",
    )
    op.drop_table("candidate_outreach_drafts")
