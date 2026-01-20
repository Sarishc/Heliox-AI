"""Add environment/project to usage snapshots

Revision ID: 014
Revises: 013
Create Date: 2026-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_snapshots", sa.Column("environment", sa.String(length=100), nullable=False, server_default="unknown"))
    op.add_column("usage_snapshots", sa.Column("project", sa.String(length=120), nullable=False, server_default="unknown"))

    op.drop_index("ix_usage_snapshots_team_date_provider_gpu", table_name="usage_snapshots")
    op.create_index(
        "ix_usage_snapshots_team_date_provider_gpu_env_project",
        "usage_snapshots",
        ["team_id", "date", "provider", "gpu_type", "environment", "project"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_snapshots_team_date_provider_gpu_env_project", table_name="usage_snapshots")
    op.create_index(
        "ix_usage_snapshots_team_date_provider_gpu",
        "usage_snapshots",
        ["team_id", "date", "provider", "gpu_type"],
        unique=False,
    )
    op.drop_column("usage_snapshots", "project")
    op.drop_column("usage_snapshots", "environment")
