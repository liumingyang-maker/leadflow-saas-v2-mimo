"""lead, company, tag, activity models

Revision ID: 0005_lead_crm_models
Revises: 0004_tenant_secrets
Create Date: 2026-06-17 07:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_lead_crm_models"
down_revision: str | None = "0004_tenant_secrets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Companies
    op.create_table(
        "companies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("size", sa.String(length=60), nullable=False),
        sa.Column("revenue_range", sa.String(length=60), nullable=False),
        sa.Column("country", sa.String(length=120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_companies")),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_companies_tenant_domain"),
    )
    op.create_index(op.f("ix_companies_tenant_id"), "companies", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_companies_domain"), "companies", ["domain"], unique=False)

    # Tags
    op.create_table(
        "tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tags")),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tags_tenant_name"),
    )
    op.create_index(op.f("ix_tags_tenant_id"), "tags", ["tenant_id"], unique=False)

    # Leads
    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("first_name", sa.String(length=120), nullable=False),
        sa.Column("last_name", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("phone", sa.String(length=60), nullable=False),
        sa.Column("website", sa.String(length=500), nullable=False),
        sa.Column("linkedin_url", sa.String(length=500), nullable=False),
        sa.Column("industry", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("import_batch_id", sa.String(length=36), nullable=False),
        sa.Column("duplicate_reason", sa.String(length=120), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('raw', 'pending_review', 'accepted', 'rejected', 'duplicate')",
            name=op.f("ck_leads_lead_status"),
        ),
        sa.CheckConstraint(
            "stage in ('new','contacted','qualified','proposal','negotiation','won','lost')",
            name=op.f("ck_leads_lead_stage"),
        ),
        sa.CheckConstraint(
            "source in ('manual', 'import', 'collection', 'inbound', 'api')",
            name=op.f("ck_leads_lead_source"),
        ),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], name=op.f("fk_leads_company_id_companies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index(op.f("ix_leads_tenant_id"), "leads", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_leads_email"), "leads", ["email"], unique=False)
    op.create_index(op.f("ix_leads_source"), "leads", ["source"], unique=False)
    op.create_index(op.f("ix_leads_status"), "leads", ["status"], unique=False)
    op.create_index(op.f("ix_leads_stage"), "leads", ["stage"], unique=False)
    op.create_index(op.f("ix_leads_is_duplicate"), "leads", ["is_duplicate"], unique=False)
    op.create_index(op.f("ix_leads_import_batch_id"), "leads", ["import_batch_id"], unique=False)
    op.create_index(op.f("ix_leads_company_id"), "leads", ["company_id"], unique=False)

    # Activities
    op.create_table(
        "activities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("old_value", sa.String(length=500), nullable=False),
        sa.Column("new_value", sa.String(length=500), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("performed_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action in ('created','imported','reviewed','accepted','rejected','stage_changed',"
            "'note_added','tagged','untagged','follow_up_set','contacted','emailed','called',"
            "'meeting','bulk_action','merged','other')",
            name=op.f("ck_activities_activity_action"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_activities_lead_id_leads")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    op.create_index(op.f("ix_activities_tenant_id"), "activities", ["tenant_id"], unique=False)
    op.create_index(op.f("ix_activities_lead_id"), "activities", ["lead_id"], unique=False)
    op.create_index(op.f("ix_activities_action"), "activities", ["action"], unique=False)

    # Lead-Tag association table
    op.create_table(
        "lead_tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=False),
        sa.Column("tag_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], name=op.f("fk_lead_tags_lead_id_leads")),
        sa.ForeignKeyConstraint(["tag_id"], ["tags.id"], name=op.f("fk_lead_tags_tag_id_tags")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_tags")),
        sa.UniqueConstraint("lead_id", "tag_id", name="uq_lead_tags_lead_tag"),
    )
    op.create_index(op.f("ix_lead_tags_lead_id"), "lead_tags", ["lead_id"], unique=False)
    op.create_index(op.f("ix_lead_tags_tag_id"), "lead_tags", ["tag_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_tags_tag_id"), table_name="lead_tags")
    op.drop_index(op.f("ix_lead_tags_lead_id"), table_name="lead_tags")
    op.drop_table("lead_tags")
    op.drop_index(op.f("ix_activities_action"), table_name="activities")
    op.drop_index(op.f("ix_activities_lead_id"), table_name="activities")
    op.drop_index(op.f("ix_activities_tenant_id"), table_name="activities")
    op.drop_table("activities")
    op.drop_index(op.f("ix_leads_company_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_import_batch_id"), table_name="leads")
    op.drop_index(op.f("ix_leads_is_duplicate"), table_name="leads")
    op.drop_index(op.f("ix_leads_stage"), table_name="leads")
    op.drop_index(op.f("ix_leads_status"), table_name="leads")
    op.drop_index(op.f("ix_leads_source"), table_name="leads")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_index(op.f("ix_leads_tenant_id"), table_name="leads")
    op.drop_table("leads")
    op.drop_index(op.f("ix_tags_tenant_id"), table_name="tags")
    op.drop_table("tags")
    op.drop_index(op.f("ix_companies_domain"), table_name="companies")
    op.drop_index(op.f("ix_companies_tenant_id"), table_name="companies")
    op.drop_table("companies")
