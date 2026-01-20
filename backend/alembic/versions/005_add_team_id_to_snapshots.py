"""Add team_id to cost and usage snapshots

Revision ID: 005b
Revises: 005a
Create Date: 2026-01-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "005b"
down_revision = "005a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add team_id columns (nullable for safe backfill)
    op.add_column(
        "cost_snapshots",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "usage_snapshots",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    
    # Foreign keys to teams
    op.create_foreign_key(
        "fk_cost_snapshots_team_id_teams",
        "cost_snapshots",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_usage_snapshots_team_id_teams",
        "usage_snapshots",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    # Update indexes to include team_id
    op.drop_index("ix_cost_snapshots_date_provider_gpu", table_name="cost_snapshots")
    op.create_index(
        "ix_cost_snapshots_team_date_provider_gpu",
        "cost_snapshots",
        ["team_id", "date", "provider", "gpu_type"],
        unique=True,
    )
    op.create_index(
        "ix_cost_snapshots_team_id",
        "cost_snapshots",
        ["team_id"],
        unique=False,
    )
    
    op.drop_index("ix_usage_snapshots_date_provider_gpu", table_name="usage_snapshots")
    op.create_index(
        "ix_usage_snapshots_team_date_provider_gpu",
        "usage_snapshots",
        ["team_id", "date", "provider", "gpu_type"],
        unique=False,
    )
    op.create_index(
        "ix_usage_snapshots_team_id",
        "usage_snapshots",
        ["team_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_usage_snapshots_team_id", table_name="usage_snapshots")
    op.drop_index("ix_usage_snapshots_team_date_provider_gpu", table_name="usage_snapshots")
    op.create_index(
        "ix_usage_snapshots_date_provider_gpu",
        "usage_snapshots",
        ["date", "provider", "gpu_type"],
        unique=False,
    )
    
    op.drop_index("ix_cost_snapshots_team_id", table_name="cost_snapshots")
    op.drop_index("ix_cost_snapshots_team_date_provider_gpu", table_name="cost_snapshots")
    op.create_index(
        "ix_cost_snapshots_date_provider_gpu",
        "cost_snapshots",
        ["date", "provider", "gpu_type"],
        unique=True,
    )
    
    op.drop_constraint("fk_usage_snapshots_team_id_teams", "usage_snapshots", type_="foreignkey")
    op.drop_constraint("fk_cost_snapshots_team_id_teams", "cost_snapshots", type_="foreignkey")
    
    op.drop_column("usage_snapshots", "team_id")
    op.drop_column("cost_snapshots", "team_id")
