"""outreach and inbound data models

Revision ID: 0009_outreach_inbound
Revises: 0008_job_model
Create Date: 2026-06-18 15:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_outreach_inbound"
down_revision: str | None = "0008_job_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_ACTIVITY_ACTIONS = (
    "action in ('created','imported','reviewed','accepted','rejected','stage_changed',"
    "'note_added','tagged','untagged','follow_up_set','contacted','emailed','called',"
    "'meeting','bulk_action','merged','other')"
)
NEW_ACTIVITY_ACTIONS = (
    "action in ('created','imported','reviewed','accepted','rejected','stage_changed',"
    "'note_added','tagged','untagged','follow_up_set','contacted','emailed','called',"
    "'meeting','bulk_action','merged','other','email_sent','email_suppressed',"
    "'email_opened','email_clicked','unsubscribed','inbound_received')"
)


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_activities")
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("activity_action", type_="check")
        batch_op.create_check_constraint("activity_action", NEW_ACTIVITY_ACTIONS)

    # Email templates
    op.create_table(
        "email_templates",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_text", sa.String(10000), nullable=False),
        sa.Column("body_html", sa.String(20000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_email_templates_tenant_name"),
    )
    op.create_index("ix_email_templates_tenant_id", "email_templates", ["tenant_id"])

    # Outreach messages
    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("body_text", sa.String(10000), nullable=False),
        sa.Column("body_html", sa.String(20000), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("provider_message_id", sa.String(120), nullable=False),
        sa.Column("error_code", sa.String(60), nullable=False),
        sa.Column("error_summary", sa.String(500), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('draft','sent','failed','suppressed')",
            name="ck_outreach_messages_outreach_msg_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_outreach_messages_tenant_id", "outreach_messages", ["tenant_id"])
    op.create_index("ix_outreach_messages_lead_id", "outreach_messages", ["lead_id"])

    # Email tracking
    op.create_table(
        "email_tracking",
        sa.Column("tracking_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column(
            "message_id", sa.String(64), sa.ForeignKey("outreach_messages.id"), nullable=False
        ),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("target_url", sa.String(2000), nullable=False),
        sa.Column("open_count", sa.Integer, nullable=False),
        sa.Column("click_count", sa.Integer, nullable=False),
        sa.Column("first_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("tracking_id"),
    )
    op.create_index("ix_email_tracking_tenant_id", "email_tracking", ["tenant_id"])
    op.create_index("ix_email_tracking_lead_id", "email_tracking", ["lead_id"])
    op.create_index("ix_email_tracking_message_id", "email_tracking", ["message_id"])

    # Suppressions
    op.create_table(
        "suppressions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("reason", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "email", name="uq_suppressions_tenant_email"),
    )
    op.create_index("ix_suppressions_tenant_id", "suppressions", ["tenant_id"])

    # Inbound tokens
    op.create_table(
        "inbound_tokens",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("token_ciphertext", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index("ix_inbound_tokens_tenant_id", "inbound_tokens", ["tenant_id"])
    op.create_index("ix_inbound_tokens_token_digest", "inbound_tokens", ["token_digest"])

    # Inbound allowed origins
    op.create_table(
        "inbound_allowed_origins",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("origin", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "origin", name="uq_inbound_origins_tenant_origin"),
    )
    op.create_index(
        "ix_inbound_allowed_origins_tenant_id", "inbound_allowed_origins", ["tenant_id"]
    )

    # Rate limits
    op.create_table(
        "inbound_rate_limits",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("scope", sa.String(120), nullable=False),
        sa.Column("bucket", sa.String(120), nullable=False),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_rate_limits_scope", "inbound_rate_limits", ["scope"])
    op.create_index("ix_inbound_rate_limits_bucket", "inbound_rate_limits", ["bucket"])

    # Idempotency
    op.create_table(
        "inbound_idempotency",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("response_json", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_idempotency_tenant_id", "inbound_idempotency", ["tenant_id"])
    op.create_index("ix_inbound_idempotency_token_digest", "inbound_idempotency", ["token_digest"])


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_activities")
    with op.batch_alter_table("activities") as batch_op:
        batch_op.drop_constraint("activity_action", type_="check")
        batch_op.create_check_constraint("activity_action", OLD_ACTIVITY_ACTIONS)

    for table_name in (
        "inbound_idempotency",
        "inbound_rate_limits",
        "inbound_allowed_origins",
        "inbound_tokens",
        "suppressions",
        "email_tracking",
        "outreach_messages",
        "email_templates",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table_name}")
