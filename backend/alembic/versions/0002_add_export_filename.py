"""Add export_filename to rewrite_jobs.

Revision ID: 0002_add_export_filename
Revises: 0001_initial
Create Date: 2026-02-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_export_filename"
down_revision: str | None = "0001_initial"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "rewrite_jobs",
        sa.Column("export_filename", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("rewrite_jobs", "export_filename")
