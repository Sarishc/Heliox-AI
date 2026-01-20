"""Add business metrics table

Revision ID: 010
Revises: 009
Create Date: 2026-01-12 02:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "business_metrics",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("revenue_usd", sa.Numeric(14, 2), nullable=False),
        sa.Column("active_users", sa.Integer(), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_business_metrics_team_date",
        "business_metrics",
        ["team_id", "date"],
        unique=True
    )
    op.create_index(
        "ix_business_metrics_team_id",
        "business_metrics",
        ["team_id"]
    )
    op.create_index(
        "ix_business_metrics_date",
        "business_metrics",
        ["date"]
    )


def downgrade() -> None:
    op.drop_index("ix_business_metrics_date", table_name="business_metrics")
    op.drop_index("ix_business_metrics_team_id", table_name="business_metrics")
    op.drop_index("uq_business_metrics_team_date", table_name="business_metrics")
    op.drop_table("business_metrics")
