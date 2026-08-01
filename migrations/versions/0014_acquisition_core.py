"""add acquisition core persistence

Revision ID: 0014_acquisition_core
Revises: 0013_admin_auth_version
Create Date: 2026-08-01 00:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_acquisition_core"
down_revision: str | None = "0013_admin_auth_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "product_knowledge_snapshots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_revision", sa.String(100), nullable=False, server_default="manual"),
        sa.Column("facts_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("prohibited_claims_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.String(36), nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_product_knowledge_snapshots"),
        sa.UniqueConstraint(
            "tenant_id", "product_name", "version", name="uq_product_snapshot_version"
        ),
    )
    op.create_index(
        "ix_product_knowledge_snapshots_tenant_id",
        "product_knowledge_snapshots",
        ["tenant_id"],
    )

    op.create_table(
        "acquisition_missions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("product_snapshot_id", sa.String(64), nullable=False),
        sa.Column("target_profile_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("channel_policy_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("budget_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("plan_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "automation_level", sa.String(32), nullable=False, server_default="research_only"
        ),
        sa.Column("cost_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("retrospective_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(36), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('draft','queued','running','paused','completed','failed','cancelled')",
            name="acquisition_mission_status",
        ),
        sa.ForeignKeyConstraint(
            ["product_snapshot_id"],
            ["product_knowledge_snapshots.id"],
            name="fk_acquisition_missions_product_snapshot_id_product_knowledge_snapshots",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acquisition_missions"),
    )
    op.create_index("ix_acquisition_missions_tenant_id", "acquisition_missions", ["tenant_id"])
    op.create_index("ix_acquisition_missions_status", "acquisition_missions", ["status"])
    op.create_index(
        "ix_acquisition_missions_product_snapshot_id",
        "acquisition_missions",
        ["product_snapshot_id"],
    )

    op.create_table(
        "acquisition_candidates",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="discovered"),
        sa.Column("entity_type", sa.String(24), nullable=False, server_default="company"),
        sa.Column("company_name", sa.String(300), nullable=False, server_default=""),
        sa.Column("domain", sa.String(253), nullable=False, server_default=""),
        sa.Column("website", sa.String(1000), nullable=False, server_default=""),
        sa.Column("hq_country_code", sa.String(2), nullable=False, server_default=""),
        sa.Column("opportunity_country_code", sa.String(2), nullable=False, server_default=""),
        sa.Column("contact_country_code", sa.String(2), nullable=False, server_default=""),
        sa.Column(
            "country_resolution_status", sa.String(24), nullable=False, server_default="unknown"
        ),
        sa.Column("source_channel", sa.String(60), nullable=False, server_default=""),
        sa.Column("source_provider", sa.String(60), nullable=False, server_default=""),
        sa.Column("contact_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("observed_facts_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("inferences_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("unknowns_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("eligibility_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("priority_score", sa.Integer(), nullable=True),
        sa.Column("priority_band", sa.String(16), nullable=False, server_default=""),
        sa.Column("signal_coverage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ai_confidence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decision_reason_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("decision_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("decided_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(500), nullable=False),
        sa.Column("promoted_lead_id", sa.String(36), nullable=False, server_default=""),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status in ('discovered','verifying','needs_evidence','eligible',"
            "'rejected','accepted','promoted')",
            name="acquisition_candidate_status",
        ),
        sa.CheckConstraint(
            "priority_score >= 0 and priority_score <= 100",
            name="candidate_priority_range",
        ),
        sa.CheckConstraint(
            "signal_coverage >= 0 and signal_coverage <= 100",
            name="candidate_coverage_range",
        ),
        sa.CheckConstraint(
            "country_resolution_status in ('unknown','confirmed','conflicting')",
            name="candidate_country_resolution_status",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["acquisition_missions.id"],
            name="fk_acquisition_candidates_mission_id_acquisition_missions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_acquisition_candidates"),
        sa.UniqueConstraint(
            "tenant_id",
            "mission_id",
            "dedupe_key",
            name="uq_candidate_mission_dedupe",
        ),
    )
    for column in (
        "tenant_id",
        "mission_id",
        "status",
        "domain",
        "opportunity_country_code",
        "source_channel",
        "eligibility_code",
        "priority_score",
        "priority_band",
        "promoted_lead_id",
    ):
        op.create_index(f"ix_acquisition_candidates_{column}", "acquisition_candidates", [column])

    op.create_table(
        "candidate_evidence",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("job_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("provider", sa.String(60), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(60), nullable=False, server_default="web"),
        sa.Column("trust_tier", sa.String(4), nullable=False, server_default="D"),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("canonical_url", sa.String(1000), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("excerpt", sa.String(4000), nullable=False, server_default=""),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "retrieved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("supports_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("validation_status", sa.String(24), nullable=False, server_default="unverified"),
        sa.CheckConstraint("trust_tier in ('A','B','C','D','E')", name="evidence_trust_tier"),
        sa.CheckConstraint(
            "validation_status in ('unverified','valid','stale','unreachable','contradicted')",
            name="evidence_validation_status",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["acquisition_candidates.id"],
            name="fk_candidate_evidence_candidate_id_acquisition_candidates",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_evidence"),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "canonical_url",
            "content_hash",
            name="uq_evidence_content",
        ),
    )
    for column in ("tenant_id", "candidate_id", "job_id"):
        op.create_index(f"ix_candidate_evidence_{column}", "candidate_evidence", [column])

    op.create_table(
        "candidate_assessments",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("candidate_id", sa.String(64), nullable=False),
        sa.Column("evidence_bundle_hash", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("score_version", sa.String(40), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("model_provider", sa.String(60), nullable=False, server_default=""),
        sa.Column("model_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("hard_gate_json", sa.Text(), nullable=False),
        sa.Column("score_breakdown_json", sa.Text(), nullable=False),
        sa.Column("signal_coverage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority_mode", sa.String(60), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        _created_at(),
        sa.CheckConstraint(
            "signal_coverage >= 0 and signal_coverage <= 100",
            name="assessment_coverage_range",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["acquisition_candidates.id"],
            name="fk_candidate_assessments_candidate_id_acquisition_candidates",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_candidate_assessments"),
        sa.UniqueConstraint(
            "tenant_id",
            "candidate_id",
            "evidence_bundle_hash",
            "policy_version",
            "score_version",
            "prompt_version",
            "model_id",
            name="uq_assessment_input_version",
        ),
    )
    op.create_index("ix_candidate_assessments_tenant_id", "candidate_assessments", ["tenant_id"])
    op.create_index(
        "ix_candidate_assessments_candidate_id", "candidate_assessments", ["candidate_id"]
    )

    op.create_table(
        "mission_suggestions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=False),
        sa.Column("suggestion_type", sa.String(60), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proposed_change_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("applied_profile_version", sa.String(60), nullable=False, server_default=""),
        sa.Column("dedupe_key", sa.String(500), nullable=False),
        _created_at(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "status in ('proposed','applied','dismissed')", name="suggestion_status"
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["acquisition_missions.id"],
            name="fk_mission_suggestions_mission_id_acquisition_missions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_mission_suggestions"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_suggestion_dedupe"),
    )
    op.create_index("ix_mission_suggestions_tenant_id", "mission_suggestions", ["tenant_id"])
    op.create_index("ix_mission_suggestions_mission_id", "mission_suggestions", ["mission_id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False, server_default=""),
        sa.Column("target_url", sa.String(500), nullable=False, server_default="/workbench"),
        sa.Column("status", sa.String(24), nullable=False, server_default="unread"),
        sa.Column("dedupe_key", sa.String(500), nullable=False),
        _created_at(),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status in ('unread','read','archived')", name="notification_status"),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
        sa.UniqueConstraint("tenant_id", "dedupe_key", name="uq_notification_dedupe"),
    )
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    op.create_table(
        "provider_statuses",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="unknown"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(80), nullable=False, server_default=""),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('unknown','healthy','degraded','failed')", name="provider_status"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_provider_statuses"),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_provider_status"),
    )
    op.create_index("ix_provider_statuses_tenant_id", "provider_statuses", ["tenant_id"])

    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(
            sa.Column("country_code", sa.String(2), nullable=False, server_default="")
        )
        batch_op.create_index("ix_companies_country_code", ["country_code"], unique=False)

    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_constraint(op.f("ck_leads_lead_source"), type_="check")
        batch_op.add_column(
            sa.Column("opportunity_country_code", sa.String(2), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("fit_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("intent_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("data_quality_score", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("priority_score", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("priority_band", sa.String(16), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("score_version", sa.String(40), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column("score_explanation_json", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.add_column(sa.Column("acquisition_candidate_id", sa.String(64), nullable=True))
        batch_op.create_check_constraint(
            op.f("ck_leads_lead_source"),
            "source in ('manual', 'import', 'collection', 'inbound', 'api', 'acquisition')",
        )
        batch_op.create_unique_constraint(
            "uq_leads_tenant_acquisition_candidate",
            ["tenant_id", "acquisition_candidate_id"],
        )
        batch_op.create_index(
            "ix_leads_opportunity_country_code", ["opportunity_country_code"], unique=False
        )
        batch_op.create_index("ix_leads_priority_score", ["priority_score"], unique=False)
        batch_op.create_index("ix_leads_priority_band", ["priority_band"], unique=False)
        batch_op.create_index(
            "ix_leads_acquisition_candidate_id", ["acquisition_candidate_id"], unique=False
        )

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_jobs_job_type"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_jobs_job_type"),
            "job_type in ('google_search', 'google_maps', 'csv_import', 'xlsx_import', "
            "'acquisition_plan', 'web_discovery', 'website_verify', 'candidate_assess', "
            "'candidate_promote', 'feedback_summarize', 'notification_dispatch', "
            "'acquisition_reconcile')",
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint(op.f("ck_jobs_job_type"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_jobs_job_type"),
            "job_type in ('google_search', 'google_maps', 'csv_import', 'xlsx_import')",
        )

    with op.batch_alter_table("leads") as batch_op:
        batch_op.drop_index("ix_leads_acquisition_candidate_id")
        batch_op.drop_index("ix_leads_priority_band")
        batch_op.drop_index("ix_leads_priority_score")
        batch_op.drop_index("ix_leads_opportunity_country_code")
        batch_op.drop_constraint("uq_leads_tenant_acquisition_candidate", type_="unique")
        batch_op.drop_constraint(op.f("ck_leads_lead_source"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_leads_lead_source"),
            "source in ('manual', 'import', 'collection', 'inbound', 'api')",
        )
        batch_op.drop_column("acquisition_candidate_id")
        batch_op.drop_column("score_explanation_json")
        batch_op.drop_column("score_version")
        batch_op.drop_column("priority_band")
        batch_op.drop_column("priority_score")
        batch_op.drop_column("data_quality_score")
        batch_op.drop_column("intent_score")
        batch_op.drop_column("fit_score")
        batch_op.drop_column("opportunity_country_code")

    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_index("ix_companies_country_code")
        batch_op.drop_column("country_code")

    op.drop_table("provider_statuses")
    op.drop_table("notifications")
    op.drop_table("mission_suggestions")
    op.drop_table("candidate_assessments")
    op.drop_table("candidate_evidence")
    op.drop_table("acquisition_candidates")
    op.drop_table("acquisition_missions")
    op.drop_table("product_knowledge_snapshots")
