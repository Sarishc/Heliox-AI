"""Add job_type and environment to jobs

Revision ID: 007
Revises: 006
Create Date: 2026-01-12 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("job_type", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("environment", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "environment")
    op.drop_column("jobs", "job_type")
