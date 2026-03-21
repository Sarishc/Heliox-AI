"""Add stripe_meter_exports for usage-based billing metering.

Revision ID: 026
Revises: 025
Create Date: 2026-04-20

- stripe_meter_exports: audit trail for Stripe meter event exports
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stripe_meter_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("stripe_identifier", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "export_date", "event_type", name="uq_stripe_meter_export_team_date_type"),
    )
    op.create_index("ix_stripe_meter_exports_team_id", "stripe_meter_exports", ["team_id"])
    op.create_index("ix_stripe_meter_exports_export_date", "stripe_meter_exports", ["export_date"])
    op.create_index("ix_stripe_meter_exports_status", "stripe_meter_exports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_stripe_meter_exports_status", table_name="stripe_meter_exports")
    op.drop_index("ix_stripe_meter_exports_export_date", table_name="stripe_meter_exports")
    op.drop_index("ix_stripe_meter_exports_team_id", table_name="stripe_meter_exports")
    op.drop_table("stripe_meter_exports")
