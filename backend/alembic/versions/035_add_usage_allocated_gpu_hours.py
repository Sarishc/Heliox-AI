"""Add allocated_gpu_hours to usage snapshots.

Idle waste used to assume 24 paid GPU-hours per day per GPU type, whatever the
fleet size. The agent now reports how many GPU-hours were powered on, which is
what idle waste is measured against. Existing rows get 0 (not measured).

Revision ID: 035
Revises: 034
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usage_snapshots",
        sa.Column(
            "allocated_gpu_hours",
            sa.Numeric(precision=14, scale=6),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("usage_snapshots", "allocated_gpu_hours")
