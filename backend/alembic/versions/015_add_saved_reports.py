"""Add saved reports, share links, and report runs

Revision ID: 015
Revises: 014
Create Date: 2026-01-20 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types via raw SQL with IF NOT EXISTS
    op.execute("CREATE TYPE IF NOT EXISTS report_run_status AS ENUM ('pending', 'running', 'completed', 'failed')")
    op.execute("CREATE TYPE IF NOT EXISTS report_file_type AS ENUM ('csv', 'pdf')")

    op.create_table(
        "saved_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_reports_team_id", "saved_reports", ["team_id"])
    op.create_index("ix_saved_reports_created_by_user_id", "saved_reports", ["created_by_user_id"])
    op.create_index("ix_saved_reports_team_created", "saved_reports", ["team_id", "created_at"])
    op.create_foreign_key(
        "fk_saved_reports_team_id",
        "saved_reports",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_saved_reports_created_by_user_id",
        "saved_reports",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "report_share_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_report_share_links_token_hash"),
    )
    op.create_index("ix_report_share_links_team_id", "report_share_links", ["team_id"])
    op.create_index("ix_report_share_links_report_id", "report_share_links", ["report_id"])
    op.create_index("ix_report_share_links_token_hash", "report_share_links", ["token_hash"])
    op.create_index("ix_report_share_links_team_report", "report_share_links", ["team_id", "report_id"])
    op.create_foreign_key(
        "fk_report_share_links_team_id",
        "report_share_links",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_report_share_links_report_id",
        "report_share_links",
        "saved_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # Create report_runs table using raw SQL to avoid SQLAlchemy enum issues
    op.execute("""
        CREATE TABLE report_runs (
            id UUID NOT NULL PRIMARY KEY,
            team_id UUID NOT NULL,
            report_id UUID NOT NULL,
            status report_run_status NOT NULL DEFAULT 'pending',
            generated_at TIMESTAMP WITH TIME ZONE,
            storage_path VARCHAR(500),
            file_type report_file_type,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.create_index("ix_report_runs_team_id", "report_runs", ["team_id"])
    op.create_index("ix_report_runs_report_id", "report_runs", ["report_id"])
    op.create_index("ix_report_runs_team_report", "report_runs", ["team_id", "report_id"])
    op.create_foreign_key(
        "fk_report_runs_team_id",
        "report_runs",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_report_runs_report_id",
        "report_runs",
        "saved_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_table("report_runs")
    op.drop_table("report_share_links")
    op.drop_table("saved_reports")
    op.execute("DROP TYPE IF EXISTS report_run_status")
    op.execute("DROP TYPE IF EXISTS report_file_type")
