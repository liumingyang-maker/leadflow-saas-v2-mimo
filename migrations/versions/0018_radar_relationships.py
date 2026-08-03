"""add cited radar relationship proposals

Revision ID: 0018_radar_relationships
Revises: 0017_radar_runs
Create Date: 2026-08-03 23:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_radar_relationships"
down_revision: str | None = "0017_radar_runs"
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
        "radar_relationships",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("source_snapshot_id", sa.String(64), nullable=False),
        sa.Column("company_name", sa.String(300), nullable=False),
        sa.Column("canonical_domain", sa.String(253), nullable=False),
        sa.Column("official_url", sa.String(1000), nullable=False),
        sa.Column("relationship_type", sa.String(24), nullable=False),
        sa.Column("evidence_strength", sa.String(24), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("evidence_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(24), nullable=False, server_default="proposed"),
        sa.Column("candidate_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("decided_by", sa.String(36), nullable=False, server_default=""),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "relationship_type in ('dealer','distributor','partner','service_network','unknown')",
            name="radar_relationship_type",
        ),
        sa.CheckConstraint(
            "evidence_strength in ('confirmed','likely','unknown')",
            name="radar_relationship_strength",
        ),
        sa.CheckConstraint(
            "status in ('proposed','converted','dismissed')", name="radar_relationship_status"
        ),
        sa.CheckConstraint("length(evidence_json) <= 20000", name="radar_relationship_evidence_size"),
        sa.ForeignKeyConstraint(["profile_id"], ["competitor_profiles.id"]),
        sa.ForeignKeyConstraint(["run_id"], ["radar_runs.id"]),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["radar_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "profile_id",
            "canonical_domain",
            "relationship_type",
            name="uq_radar_relationship_profile_domain_type",
        ),
    )
    for column in (
        "tenant_id",
        "profile_id",
        "run_id",
        "source_snapshot_id",
        "relationship_type",
        "evidence_strength",
        "status",
        "candidate_id",
    ):
        op.create_index(f"ix_radar_relationships_{column}", "radar_relationships", [column])


def downgrade() -> None:
    for column in (
        "candidate_id",
        "status",
        "evidence_strength",
        "relationship_type",
        "source_snapshot_id",
        "run_id",
        "profile_id",
        "tenant_id",
    ):
        op.drop_index(f"ix_radar_relationships_{column}", table_name="radar_relationships")
    op.drop_table("radar_relationships")
