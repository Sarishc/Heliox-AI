"""Add scope to team API keys (full or ingest-only).

Existing keys become "full", so their behaviour is unchanged.

Revision ID: 033
Revises: 032
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_api_keys",
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="full"),
    )


def downgrade() -> None:
    op.drop_column("team_api_keys", "scope")
