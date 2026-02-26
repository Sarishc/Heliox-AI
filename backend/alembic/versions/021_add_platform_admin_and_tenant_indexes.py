"""Add is_platform_admin to users and composite indexes for tenant isolation.

Revision ID: 021
Revises: 020
Create Date: 2026-02-26

"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_users_is_platform_admin", "users", ["is_platform_admin"])

    # Composite indexes for tenant-scoped queries (team_id, id)
    op.create_index(
        "ix_cost_snapshots_team_id_id",
        "cost_snapshots",
        ["team_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_usage_snapshots_team_id_id",
        "usage_snapshots",
        ["team_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_jobs_team_id_id",
        "jobs",
        ["team_id", "id"],
        unique=False,
    )
    op.create_index(
        "ix_team_members_team_id_id",
        "team_members",
        ["team_id", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_team_members_team_id_id", "team_members")
    op.drop_index("ix_jobs_team_id_id", "jobs")
    op.drop_index("ix_usage_snapshots_team_id_id", "usage_snapshots")
    op.drop_index("ix_cost_snapshots_team_id_id", "cost_snapshots")
    op.drop_index("ix_users_is_platform_admin", "users")
    op.drop_column("users", "is_platform_admin")
