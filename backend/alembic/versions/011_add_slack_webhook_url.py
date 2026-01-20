"""Add slack webhook URL to alert settings

Revision ID: 011
Revises: 010
Create Date: 2026-01-12 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("alert_settings", sa.Column("slack_webhook_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("alert_settings", "slack_webhook_url")
