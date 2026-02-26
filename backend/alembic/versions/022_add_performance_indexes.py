"""Add performance indexes for 100 concurrent users, p99 < 200ms.

Revision ID: 022
Revises: 021
Create Date: 2026-02-26

Indexes for:
- team_id + created_at (time-ordered tenant queries)
- team_id + date (cost/usage date range)
- Foreign key lookups
"""
from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # cost_snapshots: (team_id, date DESC) for date range queries
    op.create_index(
        "ix_cost_snapshots_team_date_desc",
        "cost_snapshots",
        ["team_id", "date"],
        unique=False,
        postgresql_ops={"date": "DESC"},
    )
    # usage_snapshots: (team_id, date DESC)
    op.create_index(
        "ix_usage_snapshots_team_date_desc",
        "usage_snapshots",
        ["team_id", "date"],
        unique=False,
        postgresql_ops={"date": "DESC"},
    )
    # jobs: (team_id, created_at DESC) for recent jobs
    op.create_index(
        "ix_jobs_team_created_desc",
        "jobs",
        ["team_id", "created_at"],
        unique=False,
        postgresql_ops={"created_at": "DESC"},
    )
    # team_api_keys: (team_id, is_active) for key lookup by team
    op.create_index(
        "ix_team_api_keys_team_active",
        "team_api_keys",
        ["team_id", "is_active"],
        unique=False,
    )
    # budget_policies: team_id already indexed, add composite for common query
    op.create_index(
        "ix_budget_policies_team_enabled",
        "budget_policies",
        ["team_id", "is_enabled"],
        unique=False,
    )
    # audit_logs: (team_id, created_at) for audit queries
    op.create_index(
        "ix_audit_logs_team_created",
        "audit_logs",
        ["team_id", "created_at"],
        unique=False,
        postgresql_ops={"created_at": "DESC"},
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_team_created", "audit_logs")
    op.drop_index("ix_budget_policies_team_enabled", "budget_policies")
    op.drop_index("ix_team_api_keys_team_active", "team_api_keys")
    op.drop_index("ix_jobs_team_created_desc", "jobs")
    op.drop_index("ix_usage_snapshots_team_date_desc", "usage_snapshots")
    op.drop_index("ix_cost_snapshots_team_date_desc", "cost_snapshots")
