"""Widen usage_snapshots.gpu_hours to 6 decimal places.

The agent reports every ~60s, so one report is often under 0.01 GPU-hours.
At 2 decimals each report was rounded before being added to the daily total
(a 25%-busy GPU stored 0.00 every minute), which skewed idle-waste numbers.

Revision 034 follows 032 here. Migration 033 (team API key scope) lives on a
separate branch; whichever merges second must set its down_revision to the other.

Revision ID: 034
Revises: 032
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "034"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "usage_snapshots",
        "gpu_hours",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Numeric(precision=14, scale=6),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "usage_snapshots",
        "gpu_hours",
        existing_type=sa.Numeric(precision=14, scale=6),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
    )
