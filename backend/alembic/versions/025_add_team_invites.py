"""Add team_invites for invitation flow.

Revision ID: 025
Revises: 024
Create Date: 2026-04-15

- team_invites: tokenized invite links with role and expiration
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_team_invites_team_id", "team_invites", ["team_id"])
    op.create_index("ix_team_invites_token_hash", "team_invites", ["token_hash"])
    op.create_index("ix_team_invites_email", "team_invites", ["email"])
    op.create_index("ix_team_invites_expires_at", "team_invites", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_team_invites_expires_at", table_name="team_invites")
    op.drop_index("ix_team_invites_email", table_name="team_invites")
    op.drop_index("ix_team_invites_token_hash", table_name="team_invites")
    op.drop_index("ix_team_invites_team_id", table_name="team_invites")
    op.drop_table("team_invites")
