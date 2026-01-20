"""Add budget policies and events

Revision ID: 012
Revises: 011
Create Date: 2026-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment", sa.Enum("prod", "staging", "dev", name="budget_environment"), nullable=False),
        sa.Column("project", sa.String(length=120), nullable=True),
        sa.Column("monthly_budget_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("alert_thresholds", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budget_policies_team_id", "budget_policies", ["team_id"])
    op.create_index("ix_budget_policies_environment", "budget_policies", ["environment"])
    op.create_index("ix_budget_policies_project", "budget_policies", ["project"])
    op.create_foreign_key(
        "fk_budget_policies_team_id",
        "budget_policies",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_budget_policies_scope",
        "budget_policies",
        ["team_id", "environment", "project"],
    )

    op.create_table(
        "budget_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("threshold", sa.Numeric(5, 2), nullable=False),
        sa.Column("spend_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("budget_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("predicted_breach_date", sa.Date(), nullable=True),
        sa.Column("delivered_via", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budget_events_team_id", "budget_events", ["team_id"])
    op.create_index("ix_budget_events_date", "budget_events", ["date"])
    op.create_foreign_key(
        "fk_budget_events_team_id",
        "budget_events",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_budget_events_policy_id",
        "budget_events",
        "budget_policies",
        ["budget_policy_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_budget_events_policy_id", "budget_events", type_="foreignkey")
    op.drop_constraint("fk_budget_events_team_id", "budget_events", type_="foreignkey")
    op.drop_index("ix_budget_events_date", table_name="budget_events")
    op.drop_index("ix_budget_events_team_id", table_name="budget_events")
    op.drop_table("budget_events")

    op.drop_constraint("fk_budget_policies_team_id", "budget_policies", type_="foreignkey")
    op.drop_constraint("uq_budget_policies_scope", "budget_policies", type_="unique")
    op.drop_index("ix_budget_policies_project", table_name="budget_policies")
    op.drop_index("ix_budget_policies_environment", table_name="budget_policies")
    op.drop_index("ix_budget_policies_team_id", table_name="budget_policies")
    op.drop_table("budget_policies")

    op.execute("DROP TYPE IF EXISTS budget_environment")
