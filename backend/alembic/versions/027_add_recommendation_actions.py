"""Add recommendation_actions for apply/dismiss tracking.

Revision ID: 027
Revises: 026
Create Date: 2026-04-21

- recommendation_actions: track when users apply or dismiss recommendations
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "recommendation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recommendation_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("estimated_savings_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("recommendation_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("applied_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("gpu_type", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["applied_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id",
            "recommendation_fingerprint",
            name="uq_recommendation_action_team_fingerprint",
        ),
    )
    op.create_index("ix_recommendation_actions_team_id", "recommendation_actions", ["team_id"])
    op.create_index("ix_recommendation_actions_recommendation_fingerprint", "recommendation_actions", ["recommendation_fingerprint"])
    op.create_index("ix_recommendation_actions_status", "recommendation_actions", ["status"])
    op.create_index("ix_recommendation_actions_team_status", "recommendation_actions", ["team_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_recommendation_actions_team_status", table_name="recommendation_actions")
    op.drop_index("ix_recommendation_actions_status", table_name="recommendation_actions")
    op.drop_index("ix_recommendation_actions_recommendation_fingerprint", table_name="recommendation_actions")
    op.drop_index("ix_recommendation_actions_team_id", table_name="recommendation_actions")
    op.drop_table("recommendation_actions")
