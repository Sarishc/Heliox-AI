"""Add experiment framework tables

Revision ID: 009
Revises: 008
Create Date: 2026-01-12 02:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("baseline_policy", sa.String(length=255), nullable=False),
        sa.Column("optimized_policy", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiments_team_dates", "experiments", ["team_id", "start_date", "end_date"])

    op.create_table(
        "experiment_assignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("group", sa.String(length=50), nullable=False),
        sa.Column("assigned_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiment_assignments_group", "experiment_assignments", ["experiment_id", "group"])
    op.create_index("uq_experiment_job", "experiment_assignments", ["experiment_id", "job_id"], unique=True)

    op.create_table(
        "experiment_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("experiment_id", sa.UUID(), nullable=False),
        sa.Column("computed_at", sa.DateTime(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("experiment_id"),
    )
    op.create_index("ix_experiment_results_experiment_id", "experiment_results", ["experiment_id"])


def downgrade() -> None:
    op.drop_index("ix_experiment_results_experiment_id", table_name="experiment_results")
    op.drop_table("experiment_results")
    op.drop_index("uq_experiment_job", table_name="experiment_assignments")
    op.drop_index("ix_experiment_assignments_group", table_name="experiment_assignments")
    op.drop_table("experiment_assignments")
    op.drop_index("ix_experiments_team_dates", table_name="experiments")
    op.drop_table("experiments")
