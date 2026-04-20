"""Add inference_spans and model_cost_summaries tables for per-request cost attribution.

Revision ID: 031
Revises: 030
Create Date: 2026-04-20 00:00:00.000000

Changes:
  1. inference_spans — individual OTel/simplified inference request records.
     Cost fields (cost_usd, cost_per_1k_tokens) start as NULL and are
     populated asynchronously by the attribution engine after GPU cost data
     arrives for the same cluster/day.
  2. model_cost_summaries — pre-aggregated daily rollup per (team, model,
     cluster). Written by the nightly rollup task; queried by the dashboard.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. inference_spans ───────────────────────────────────────────────────
    op.create_table(
        "inference_spans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),

        # Ownership
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),

        # Model identification
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("serving_framework", sa.String(50), nullable=False,
                  server_default="custom"),
        sa.Column("cluster_name", sa.String(200), nullable=True),

        # Request tracing
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("trace_id", sa.String(128), nullable=True),

        # Token counts
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),

        # Latency
        sa.Column("duration_ms", sa.Float, nullable=False),
        sa.Column("ttfb_ms", sa.Float, nullable=True),

        # GPU context
        sa.Column("gpu_type", sa.String(100), nullable=True),
        sa.Column("gpu_count", sa.Integer, nullable=True),

        # Attributed costs (written by attribution engine)
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("cost_per_1k_tokens", sa.Float, nullable=True),

        # Timestamps
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),

        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
    )

    op.create_index(
        "ix_inference_spans_team_id",
        "inference_spans", ["team_id"],
    )
    op.create_index(
        "ix_inference_spans_team_model_started",
        "inference_spans", ["team_id", "model_name", "started_at"],
    )
    op.create_index(
        "ix_inference_spans_team_cost_null",
        "inference_spans", ["team_id", "started_at"],
    )
    op.create_index(
        "ix_inference_spans_team_cluster_started",
        "inference_spans", ["team_id", "cluster_name", "started_at"],
    )

    # ── 2. model_cost_summaries ──────────────────────────────────────────────
    op.create_table(
        "model_cost_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),

        # Ownership + dimensions
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(255), nullable=False),
        sa.Column("serving_framework", sa.String(50), nullable=False,
                  server_default="custom"),
        sa.Column("cluster_name", sa.String(200), nullable=True),
        sa.Column("date", sa.Date, nullable=False),

        # Request volume
        sa.Column("request_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_output_tokens", sa.Integer, nullable=False, server_default="0"),

        # Cost
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("avg_cost_per_request", sa.Float, nullable=False, server_default="0"),
        sa.Column("avg_cost_per_1k_tokens", sa.Float, nullable=True),
        sa.Column("p99_cost_per_request", sa.Float, nullable=True),

        # Performance
        sa.Column("avg_duration_ms", sa.Float, nullable=False, server_default="0"),
        sa.Column("p99_duration_ms", sa.Float, nullable=True),
        sa.Column("error_count", sa.Integer, nullable=False, server_default="0"),

        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "team_id", "model_name", "cluster_name", "date",
            name="uq_model_cost_summary_team_model_cluster_date",
        ),
    )

    op.create_index(
        "ix_model_cost_summaries_team_id",
        "model_cost_summaries", ["team_id"],
    )
    op.create_index(
        "ix_model_cost_summaries_team_date",
        "model_cost_summaries", ["team_id", "date"],
    )
    op.create_index(
        "ix_model_cost_summaries_team_model",
        "model_cost_summaries", ["team_id", "model_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_model_cost_summaries_team_model", table_name="model_cost_summaries")
    op.drop_index("ix_model_cost_summaries_team_date", table_name="model_cost_summaries")
    op.drop_index("ix_model_cost_summaries_team_id", table_name="model_cost_summaries")
    op.drop_table("model_cost_summaries")

    op.drop_index("ix_inference_spans_team_cluster_started", table_name="inference_spans")
    op.drop_index("ix_inference_spans_team_cost_null", table_name="inference_spans")
    op.drop_index("ix_inference_spans_team_model_started", table_name="inference_spans")
    op.drop_index("ix_inference_spans_team_id", table_name="inference_spans")
    op.drop_table("inference_spans")
