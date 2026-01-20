"""Add team_members, audit_logs, api_usage, team_daily_rollups

Revision ID: 006
Revises: 005b
Create Date: 2026-01-12 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Enum("owner", "admin", "viewer", name="team_role"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])
    op.create_unique_constraint("uq_team_members_team_user", "team_members", ["team_id", "user_id"])
    op.create_foreign_key(
        "fk_team_members_team_id",
        "team_members",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_team_members_user_id",
        "team_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_team_id", "audit_logs", ["team_id"])
    op.create_foreign_key(
        "fk_audit_logs_team_id",
        "audit_logs",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    op.create_table(
        "api_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("endpoint", sa.String(length=255), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_api_usage_team_id", "api_usage", ["team_id"])
    op.create_index("ix_api_usage_date", "api_usage", ["date"])
    op.create_unique_constraint("uq_api_usage_team_date_endpoint", "api_usage", ["team_id", "date", "endpoint"])
    op.create_foreign_key(
        "fk_api_usage_team_id",
        "api_usage",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    
    op.create_table(
        "team_daily_rollups",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("total_cost_usd", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("total_gpu_hours", sa.Numeric(precision=12, scale=2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_daily_rollups_team_id", "team_daily_rollups", ["team_id"])
    op.create_index("ix_team_daily_rollups_date", "team_daily_rollups", ["date"])
    op.create_unique_constraint(
        "ix_team_daily_rollups_team_date", "team_daily_rollups", ["team_id", "date"]
    )
    op.create_foreign_key(
        "fk_team_daily_rollups_team_id",
        "team_daily_rollups",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_team_daily_rollups_team_id", "team_daily_rollups", type_="foreignkey")
    op.drop_index("ix_team_daily_rollups_date", table_name="team_daily_rollups")
    op.drop_index("ix_team_daily_rollups_team_id", table_name="team_daily_rollups")
    op.drop_constraint("ix_team_daily_rollups_team_date", "team_daily_rollups", type_="unique")
    op.drop_table("team_daily_rollups")
    
    op.drop_constraint("fk_api_usage_team_id", "api_usage", type_="foreignkey")
    op.drop_constraint("uq_api_usage_team_date_endpoint", "api_usage", type_="unique")
    op.drop_index("ix_api_usage_date", table_name="api_usage")
    op.drop_index("ix_api_usage_team_id", table_name="api_usage")
    op.drop_table("api_usage")
    
    op.drop_constraint("fk_audit_logs_team_id", "audit_logs", type_="foreignkey")
    op.drop_index("ix_audit_logs_team_id", table_name="audit_logs")
    op.drop_table("audit_logs")
    
    op.drop_constraint("fk_team_members_user_id", "team_members", type_="foreignkey")
    op.drop_constraint("fk_team_members_team_id", "team_members", type_="foreignkey")
    op.drop_constraint("uq_team_members_team_user", "team_members", type_="unique")
    op.drop_index("ix_team_members_user_id", table_name="team_members")
    op.drop_index("ix_team_members_team_id", table_name="team_members")
    op.drop_table("team_members")
    
    op.execute("DROP TYPE IF EXISTS team_role")
