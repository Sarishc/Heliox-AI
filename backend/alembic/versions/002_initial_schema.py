"""Initial schema for core tables

Revision ID: 002
Revises: None
Create Date: 2026-01-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_teams_name", "teams", ["name"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", sa.String(length=100), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("gpu_type", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=True),
        sa.Column("end_time", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_jobs_job_id", "jobs", ["job_id"], unique=True)
    op.create_index("ix_jobs_team_id", "jobs", ["team_id"])
    op.create_index("ix_jobs_provider_gpu_type", "jobs", ["provider", "gpu_type"])
    op.create_foreign_key(
        "fk_jobs_team_id",
        "jobs",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "cost_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("gpu_type", sa.String(length=100), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cost_snapshots_date", "cost_snapshots", ["date"])

    op.create_table(
        "usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("gpu_type", sa.String(length=100), nullable=False),
        sa.Column("gpu_hours", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_snapshots_date", "usage_snapshots", ["date"])


def downgrade() -> None:
    op.drop_index("ix_usage_snapshots_date", table_name="usage_snapshots")
    op.drop_table("usage_snapshots")

    op.drop_index("ix_cost_snapshots_date", table_name="cost_snapshots")
    op.drop_table("cost_snapshots")

    op.drop_constraint("fk_jobs_team_id", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_provider_gpu_type", table_name="jobs")
    op.drop_index("ix_jobs_team_id", table_name="jobs")
    op.drop_index("ix_jobs_job_id", table_name="jobs")
    op.drop_table("jobs")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.drop_index("ix_teams_name", table_name="teams")
    op.drop_table("teams")
