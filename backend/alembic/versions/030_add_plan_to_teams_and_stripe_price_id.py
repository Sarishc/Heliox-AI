"""Add plan column to teams and stripe_price_id to team_subscriptions.

Revision ID: 030
Revises: 029
Create Date: 2026-04-20 00:00:00.000000

Changes:
  1. teams.plan (VARCHAR, default 'free', not null) — denormalized cache of the
     team's billing plan for fast enforcement at the route layer without a join.
  2. team_subscriptions.stripe_price_id (VARCHAR, nullable) — tracks which
     Stripe price ID the team is subscribed to for plan-from-price-id resolution.
  3. Backfill teams.plan = 'free' for all existing rows.
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add plan column to teams table
    op.add_column(
        "teams",
        sa.Column(
            "plan",
            sa.String(50),
            nullable=False,
            server_default="free",
            comment="Denormalized billing plan (free/starter/growth/enterprise)",
        ),
    )
    op.create_index("ix_teams_plan", "teams", ["plan"])

    # Backfill: all existing teams start on free
    op.execute("UPDATE teams SET plan = 'free' WHERE plan IS NULL OR plan = ''")

    # 2. Add stripe_price_id to team_subscriptions
    op.add_column(
        "team_subscriptions",
        sa.Column(
            "stripe_price_id",
            sa.String(255),
            nullable=True,
            comment="Active Stripe price ID — used to map subscription to plan tier",
        ),
    )
    op.create_index(
        "ix_team_subscriptions_stripe_price_id",
        "team_subscriptions",
        ["stripe_price_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_team_subscriptions_stripe_price_id", table_name="team_subscriptions")
    op.drop_column("team_subscriptions", "stripe_price_id")

    op.drop_index("ix_teams_plan", table_name="teams")
    op.drop_column("teams", "plan")
