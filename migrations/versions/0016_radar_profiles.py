"""add tenant-owned competitor radar profiles

Revision ID: 0016_radar_profiles
Revises: 0015_browser_foundation
Create Date: 2026-08-03 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_radar_profiles"
down_revision: str | None = "0015_browser_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def upgrade() -> None:
    op.create_table(
        "radar_competitor_suggestions",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("official_url", sa.String(1000), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("decided_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status in ('proposed','approved','dismissed')",
            name="radar_suggestion_status",
        ),
        sa.CheckConstraint(
            "length(evidence_hash) = 64",
            name="radar_suggestion_evidence_hash_length",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["acquisition_missions.id"],
            name="fk_radar_competitor_suggestions_mission_id_acquisition_missions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_radar_competitor_suggestions"),
        sa.UniqueConstraint(
            "tenant_id",
            "mission_id",
            "canonical_domain",
            name="uq_radar_suggestion_mission_domain",
        ),
    )
    for column in ("tenant_id", "mission_id", "status"):
        op.create_index(
            f"ix_radar_competitor_suggestions_{column}",
            "radar_competitor_suggestions",
            [column],
        )

    op.create_table(
        "competitor_profiles",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("mission_id", sa.String(64), nullable=False),
        sa.Column("product_snapshot_id", sa.String(64), nullable=False),
        sa.Column("source_suggestion_id", sa.String(64), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("official_url", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("tracking_config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("approved_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status in ('active','paused','archived')",
            name="competitor_profile_status",
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["acquisition_missions.id"],
            name="fk_competitor_profiles_mission_id_acquisition_missions",
        ),
        sa.ForeignKeyConstraint(
            ["product_snapshot_id"],
            ["product_knowledge_snapshots.id"],
            name="fk_competitor_profiles_product_snapshot_id_product_knowledge_snapshots",
        ),
        sa.ForeignKeyConstraint(
            ["source_suggestion_id"],
            ["radar_competitor_suggestions.id"],
            name="fk_competitor_profiles_source_suggestion_id_radar_competitor_suggestions",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_competitor_profiles"),
        sa.UniqueConstraint(
            "tenant_id",
            "mission_id",
            "canonical_domain",
            name="uq_competitor_profile_mission_domain",
        ),
    )
    for column in ("tenant_id", "mission_id", "product_snapshot_id", "source_suggestion_id", "status"):
        op.create_index(f"ix_competitor_profiles_{column}", "competitor_profiles", [column])


def downgrade() -> None:
    for column in ("status", "source_suggestion_id", "product_snapshot_id", "mission_id", "tenant_id"):
        op.drop_index(f"ix_competitor_profiles_{column}", table_name="competitor_profiles")
    op.drop_table("competitor_profiles")
    for column in ("status", "mission_id", "tenant_id"):
        op.drop_index(
            f"ix_radar_competitor_suggestions_{column}",
            table_name="radar_competitor_suggestions",
        )
    op.drop_table("radar_competitor_suggestions")
