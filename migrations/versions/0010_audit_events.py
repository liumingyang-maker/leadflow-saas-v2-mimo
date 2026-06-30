"""audit events table

Revision ID: 0010_audit_events
Revises: 0009_outreach_inbound
Create Date: 2026-06-18 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_audit_events"
down_revision: str | None = "0009_outreach_inbound"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=True),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_admin_id", sa.String(64), nullable=False),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("target_type", sa.String(60), nullable=False),
        sa.Column("target_id", sa.String(64), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("user_agent_hash", sa.String(64), nullable=False),
        sa.Column("safe_summary", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "actor_type in ('user','admin','system')", name=op.f("ck_audit_events_audit_actor_type")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])


def downgrade() -> None:
    op.drop_table("audit_events")
