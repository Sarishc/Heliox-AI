"""Add project field to jobs

Revision ID: 013
Revises: 012
Create Date: 2026-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("project", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "project")
