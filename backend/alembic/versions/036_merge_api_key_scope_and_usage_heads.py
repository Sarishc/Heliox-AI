"""Merge the API-key-scope and usage-precision migration branches.

Migrations 033 (team API key scope, PR #8) and 034 (usage gpu_hours precision,
PR #9) were both written against 032, so main had two heads and
``alembic upgrade head`` failed. 035 (allocated GPU-hours, PR #10) follows 034.

This revision only joins the two branches; it changes no schema. Existing
migrations are left exactly as merged, so any database that already applied
033, 034 or 035 upgrades normally:

    fresh          -> 001 ... 035, then 036
    at 033         -> 034, 035, 036
    at 034 or 035  -> (035), 033, 036
    at 033 and 034 -> 035, 036

Revision ID: 036
Revises: 033, 035
Create Date: 2026-10-28
"""

revision = "036"
down_revision = ("033", "035")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
