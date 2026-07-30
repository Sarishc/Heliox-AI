"""Add optional expiry timestamp to team API keys.

Revision ID: 032
Revises: 031
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_team_api_keys_expires_at",
        "team_api_keys",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_team_api_keys_expires_at", table_name="team_api_keys")
    op.drop_column("team_api_keys", "expires_at")
