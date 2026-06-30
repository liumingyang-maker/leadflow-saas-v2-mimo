"""add rows_json to import_batches for server-side row storage

Revision ID: 0007_import_batch_rows
Revises: 0006_import_batch
Create Date: 2026-06-17 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_import_batch_rows"
down_revision: str | None = "0006_import_batch"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "import_batches",
        sa.Column("rows_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("import_batches", "rows_json")
