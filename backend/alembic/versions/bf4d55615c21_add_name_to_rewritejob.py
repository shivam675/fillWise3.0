from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = 'bf4d55615c21'
down_revision: str | None = '0002_add_export_filename'
branch_labels: str | None = None
depends_on: str | None = None

def upgrade() -> None:
    op.add_column('rewrite_jobs', sa.Column('name', sa.String(length=200), nullable=True))

def downgrade() -> None:
    op.drop_column('rewrite_jobs', 'name')
