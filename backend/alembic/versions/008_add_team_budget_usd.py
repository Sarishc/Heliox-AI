"""Add monthly budget to teams

Revision ID: 008
Revises: 007
Create Date: 2026-01-12 02:05:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("teams", "monthly_budget_usd")
