"""Inference span and cost summary models for per-request cost attribution."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class InferenceSpan(Base, UUIDMixin, TimestampMixin):
    """Individual inference request record ingested from OTel spans or simplified format.

    Cost fields are populated asynchronously by the attribution engine
    after GPU cost data for the same time window arrives.
    """

    __tablename__ = "inference_spans"

    # ── Ownership ─────────────────────────────────────────────────────────────
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Team that owns this inference record",
    )

    # ── Model identification ───────────────────────────────────────────────────
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Model identifier, e.g. 'llama-3-70b', 'stable-diffusion-xl'",
    )
    model_version: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Optional model version tag",
    )
    serving_framework: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="custom",
        comment="Serving framework: vllm | tgi | triton | custom",
    )
    cluster_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        index=True,
        comment="Cluster/integration name — used to join with CostSnapshot.provider",
    )

    # ── Request tracing ────────────────────────────────────────────────────────
    request_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="OTel span_id or X-Request-ID",
    )
    trace_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="OTel trace_id for distributed tracing correlation",
    )

    # ── Token counts (LLM-specific) ────────────────────────────────────────────
    input_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Prompt / input token count",
    )
    output_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Completion / output token count",
    )
    total_tokens: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Total tokens (input + output); stored for fast aggregation",
    )

    # ── Latency ───────────────────────────────────────────────────────────────
    duration_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Total request duration in milliseconds",
    )
    ttfb_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Time-to-first-byte in ms (streaming responses only)",
    )

    # ── GPU context ───────────────────────────────────────────────────────────
    gpu_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="GPU type resolved from cluster context, e.g. A100",
    )
    gpu_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of GPUs serving this request",
    )

    # ── Attributed costs (written by attribution engine) ──────────────────────
    cost_usd: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Attributed USD cost for this request; NULL until attribution runs",
    )
    cost_per_1k_tokens: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Cost per 1,000 tokens; NULL if token counts unavailable",
    )

    # ── Timestamps ────────────────────────────────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the inference request started",
    )
    ended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the inference request completed",
    )

    __table_args__ = (
        # Primary lookup: team + model + time window
        Index("ix_inference_spans_team_model_started", "team_id", "model_name", "started_at"),
        # Attribution engine polls for uncosted spans
        Index("ix_inference_spans_team_cost_null", "team_id", "started_at"),
        # Cluster join for attribution
        Index("ix_inference_spans_team_cluster_started", "team_id", "cluster_name", "started_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<InferenceSpan(model={self.model_name}, "
            f"tokens={self.total_tokens}, cost={self.cost_usd})>"
        )


class ModelCostSummary(Base, UUIDMixin, TimestampMixin):
    """Pre-aggregated daily rollup of inference costs per model.

    Written by the nightly rollup task; queried by the dashboard.
    """

    __tablename__ = "model_cost_summaries"

    # ── Ownership + dimensions ────────────────────────────────────────────────
    team_id: Mapped[UUID] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Team that owns this summary",
    )
    model_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Model identifier",
    )
    serving_framework: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="custom",
        comment="Serving framework",
    )
    cluster_name: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Cluster name (NULL = all clusters aggregated)",
    )
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="The day this summary covers (UTC)",
    )

    # ── Request volume ─────────────────────────────────────────────────────────
    request_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Total inference requests on this day",
    )
    total_input_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sum of input tokens across all requests",
    )
    total_output_tokens: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Sum of output tokens across all requests",
    )

    # ── Cost ──────────────────────────────────────────────────────────────────
    total_cost_usd: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Total attributed cost for the day",
    )
    avg_cost_per_request: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Mean cost per inference request",
    )
    avg_cost_per_1k_tokens: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="Mean cost per 1,000 total tokens; NULL if no token data",
    )
    p99_cost_per_request: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="99th-percentile cost per request",
    )

    # ── Performance ───────────────────────────────────────────────────────────
    avg_duration_ms: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        comment="Mean request duration in milliseconds",
    )
    p99_duration_ms: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
        comment="99th-percentile request duration in milliseconds",
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of failed/errored requests on this day",
    )

    __table_args__ = (
        # Idempotent upsert key
        UniqueConstraint(
            "team_id", "model_name", "cluster_name", "date",
            name="uq_model_cost_summary_team_model_cluster_date",
        ),
        Index("ix_model_cost_summaries_team_date", "team_id", "date"),
        Index("ix_model_cost_summaries_team_model", "team_id", "model_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModelCostSummary(model={self.model_name}, "
            f"date={self.date}, cost=${self.total_cost_usd:.4f})>"
        )
