"""add gcp_billing_bigquery provider

Revision ID: 017
Revises: 016
Create Date: 2026-01-30 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum value to integrationprovider
    op.execute("ALTER TYPE integrationprovider ADD VALUE IF NOT EXISTS 'gcp_billing_bigquery'")


def downgrade() -> None:
    # PostgreSQL doesn't support removing enum values
    # Would need to recreate the enum type and update all references
    pass
