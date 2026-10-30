"""
Cost source ledger models (migration 038).

Schema only: nothing in the application reads or writes these tables yet. They hold every
provider observation of every cost line, decide which source stream is authoritative for an
account and day, and record canonical billing facts. The *_gate_* CHECK constraints keep the
ledger shadow-only: no team can be live, no billing fact billable, no reconciliation applied.

Every definition here must match alembic/versions/038_cost_source_ledger.py exactly;
tests/test_migration_038_parity_postgres.py compares the two. Trigger functions and triggers
are PostgreSQL-only and come from app.models.cost_ledger_ddl.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    DDL,
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    LargeBinary,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.cost_ledger_ddl import (
    GUARD_FUNCTION_V1,
    GUARDED_TABLES_V1,
    RECORD_DELETE_GUARD_FUNCTION_V1,
    RECORD_DELETE_TRIGGER_V1,
    guard_trigger_v1,
)

TZ = DateTime(timezone=True)
AMOUNT = Numeric(24, 10)
FX_RATE = Numeric(24, 12)
CHARGE_CLASSES = "'usage','credit','refund','discount','tax','fee','support','adjustment','rounding'"


def _deferred_fk(columns, refcolumns, name=None, **kw) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(columns, refcolumns, name=name, deferrable=True, initially="DEFERRED", **kw)


def _deferred_user_fk() -> ForeignKey:
    return ForeignKey("users.id", deferrable=True, initially="DEFERRED")


class TeamCostLedgerSettings(Base):
    """Per-team ledger mode. No row means 'off'."""

    __tablename__ = "team_cost_ledger_settings"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    ledger_mode: Mapped[str] = mapped_column(String(8), nullable=False, default="off", server_default="off")
    billing_pathway: Mapped[str] = mapped_column(String(8), nullable=False, default="legacy", server_default="legacy")
    billing_basis: Mapped[str] = mapped_column(
        String(24), nullable=False, default="legacy_saved_rows", server_default="legacy_saved_rows"
    )
    changed_by: Mapped[Optional[UUID]] = mapped_column(_deferred_user_fk())
    changed_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "ledger_mode IN ('off','shadow','live')\n"
            "    AND billing_pathway IN ('legacy','ledger') AND billing_basis IN ('legacy_saved_rows','first_ingested')",
            name="ck_ledger_settings_values",
        ),
        CheckConstraint(
            "billing_pathway = 'legacy' OR ledger_mode = 'live'", name="ck_ledger_settings_pathway_requires_live"
        ),
        CheckConstraint("ledger_mode IN ('off','shadow')", name="ck_ledger_settings_gate_no_live"),
        CheckConstraint(
            "billing_pathway = 'legacy' AND billing_basis = 'legacy_saved_rows'",
            name="ck_ledger_settings_gate_legacy_billing",
        ),
        Index("ix_team_cost_ledger_settings_changed_by", "changed_by"),
    )


class CostSourceStream(Base):
    """One way of observing one usage account (vantage, metric, grouping layout, query config)."""

    __tablename__ = "cost_source_streams"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    vantage: Mapped[str] = mapped_column(String(256), nullable=False)
    metric: Mapped[str] = mapped_column(String(64), nullable=False)
    grouping_version: Mapped[str] = mapped_column(String(64), nullable=False)
    config_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("source_kind IN ('provider','manual')", name="ck_streams_kind"),
        CheckConstraint(
            "role IN ('cost','attribution') AND (source_kind = 'provider' OR role = 'cost')", name="ck_streams_role"
        ),
        CheckConstraint("provider <> '' AND provider = lower(provider)", name="ck_streams_provider"),
        CheckConstraint("length(config_sha256) = 32", name="ck_streams_config_sha256"),
        CheckConstraint("(source_kind = 'manual') = (scope_type = 'manual')", name="ck_streams_manual_scope"),
        CheckConstraint(
            "(source_kind = 'provider' AND usage_account LIKE provider || ':%:%')\n"
            "    OR (source_kind = 'manual' AND usage_account LIKE 'manual:%')",
            name="ck_streams_account_prefix",
        ),
        UniqueConstraint(
            "team_id",
            "source_kind",
            "role",
            "provider",
            "scope_type",
            "billing_account",
            "usage_account",
            "vantage",
            "metric",
            "grouping_version",
            "config_sha256",
            name="uq_cost_source_streams_identity",
        ),
        UniqueConstraint("team_id", "id", name="uq_cost_source_streams_team_id"),
        UniqueConstraint("team_id", "id", "source_kind", name="uq_cost_source_streams_team_id_kind"),
        UniqueConstraint(
            "team_id",
            "id",
            "provider",
            "billing_account",
            "usage_account",
            "role",
            name="uq_cost_source_streams_team_id_account_role",
        ),
    )


class CostSourceStreamBinding(Base):
    """Which connections feed a stream (a stream may be fed by several)."""

    __tablename__ = "cost_source_stream_bindings"

    team_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    connection_id: Mapped[UUID] = mapped_column(nullable=False)
    bound_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    unbound_at: Mapped[Optional[datetime]] = mapped_column(TZ)

    __table_args__ = (
        PrimaryKeyConstraint("stream_id", "connection_id"),
        ForeignKeyConstraint(
            ["team_id", "stream_id"],
            ["cost_source_streams.team_id", "cost_source_streams.id"],
            name="fk_bindings_stream",
            ondelete="CASCADE",
        ),
        _deferred_fk(
            ["team_id", "connection_id"],
            ["integration_connections.team_id", "integration_connections.id"],
            name="fk_bindings_connection",
        ),
        CheckConstraint("unbound_at IS NULL OR unbound_at >= bound_at", name="ck_bindings_interval"),
        Index("ix_bindings_team_connection", "team_id", "connection_id"),
        Index("ix_bindings_team_stream", "team_id", "stream_id"),
    )


class CostSourceAuthority(Base):
    """Configured authoritative cost stream for a usage account."""

    __tablename__ = "cost_source_authority"

    team_id: Mapped[UUID] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_role: Mapped[str] = mapped_column(String(12), nullable=False, default="cost", server_default="cost")
    set_by: Mapped[UUID] = mapped_column(_deferred_user_fk(), nullable=False)
    set_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("team_id", "provider", "billing_account", "usage_account"),
        CheckConstraint("stream_role = 'cost'", name="ck_authority_cost_role"),
        ForeignKeyConstraint(
            ["team_id", "stream_id", "provider", "billing_account", "usage_account", "stream_role"],
            [
                "cost_source_streams.team_id",
                "cost_source_streams.id",
                "cost_source_streams.provider",
                "cost_source_streams.billing_account",
                "cost_source_streams.usage_account",
                "cost_source_streams.role",
            ],
            name="fk_authority_stream",
            ondelete="CASCADE",
        ),
        Index(
            "ix_authority_stream", "team_id", "stream_id", "provider", "billing_account", "usage_account", "stream_role"
        ),
        Index("ix_authority_set_by", "set_by"),
    )


class CostSourceAuthorityHistory(Base):
    """Append-only history of authority changes."""

    __tablename__ = "cost_source_authority_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    from_stream_id: Mapped[Optional[UUID]] = mapped_column()
    to_stream_id: Mapped[UUID] = mapped_column(nullable=False)
    changed_by: Mapped[UUID] = mapped_column(_deferred_user_fk(), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_authority_history_account", "team_id", "provider", "billing_account", "usage_account", "changed_at"),
        Index("ix_authority_history_changed_by", "changed_by"),
    )


class CostSourceStreamDay(Base):
    """Latest complete publication of one stream for one usage day."""

    __tablename__ = "cost_source_stream_days"

    team_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_fetch_started_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    last_run_id: Mapped[UUID] = mapped_column(nullable=False)
    last_connection_id: Mapped[UUID] = mapped_column(nullable=False)
    last_fencing_token: Mapped[int] = mapped_column(BigInteger, nullable=False)
    record_count: Mapped[int] = mapped_column(nullable=False)
    converted_total_usd: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    unconverted_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    provider_total_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    attribution_status: Mapped[Optional[str]] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("stream_id", "usage_date"),
        CheckConstraint("state IN ('estimated','final','suspect_empty')", name="ck_stream_days_state"),
        CheckConstraint(
            "generation > 0 AND record_count >= 0 AND unconverted_count >= 0", name="ck_stream_days_counts"
        ),
        CheckConstraint(
            "attribution_status IS NULL OR attribution_status IN ('reconciled','mismatch','no_cost_coverage')",
            name="ck_stream_days_attribution",
        ),
        UniqueConstraint("team_id", "stream_id", "usage_date", name="uq_stream_days_team"),
        ForeignKeyConstraint(
            ["team_id", "stream_id"],
            ["cost_source_streams.team_id", "cost_source_streams.id"],
            name="fk_stream_days_stream",
            ondelete="CASCADE",
        ),
        _deferred_fk(
            ["last_run_id", "last_connection_id"],
            ["integration_sync_runs.id", "integration_sync_runs.connection_id"],
            name="fk_stream_days_run",
        ),
        _deferred_fk(
            ["team_id", "last_connection_id"],
            ["integration_connections.team_id", "integration_connections.id"],
            name="fk_stream_days_connection",
        ),
        Index("ix_stream_days_run", "last_run_id", "last_connection_id"),
        Index("ix_stream_days_connection", "team_id", "last_connection_id"),
    )


class CostSourceCoverage(Base):
    """Per usage account and day: the one authoritative cost stream and its state."""

    __tablename__ = "cost_source_coverage"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    authoritative_stream_id: Mapped[UUID] = mapped_column(nullable=False)
    authoritative_role: Mapped[str] = mapped_column(String(12), nullable=False, default="cost", server_default="cost")
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    authority_source: Mapped[str] = mapped_column(String(20), nullable=False)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("team_id", "provider", "billing_account", "usage_account", "usage_date"),
        CheckConstraint("authoritative_role = 'cost'", name="ck_coverage_cost_role"),
        CheckConstraint("state IN ('estimated','final','conflict','suspect_empty')", name="ck_coverage_state"),
        CheckConstraint(
            "authority_source IN ('configured','default_precedence','reviewed')", name="ck_coverage_authority_source"
        ),
        CheckConstraint("generation > 0", name="ck_coverage_generation"),
        ForeignKeyConstraint(
            [
                "team_id",
                "authoritative_stream_id",
                "provider",
                "billing_account",
                "usage_account",
                "authoritative_role",
            ],
            [
                "cost_source_streams.team_id",
                "cost_source_streams.id",
                "cost_source_streams.provider",
                "cost_source_streams.billing_account",
                "cost_source_streams.usage_account",
                "cost_source_streams.role",
            ],
            name="fk_coverage_stream",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["team_id", "authoritative_stream_id", "usage_date"],
            [
                "cost_source_stream_days.team_id",
                "cost_source_stream_days.stream_id",
                "cost_source_stream_days.usage_date",
            ],
            name="fk_coverage_stream_day",
            ondelete="CASCADE",
        ),
        Index("ix_coverage_stream_day", "team_id", "authoritative_stream_id", "usage_date"),
        Index(
            "ix_coverage_stream",
            "team_id",
            "authoritative_stream_id",
            "provider",
            "billing_account",
            "usage_account",
            "authoritative_role",
        ),
    )


class CostSourceConflict(Base):
    """A witness stream disagreeing with the authoritative stream: quarantined, never accepted."""

    __tablename__ = "cost_source_conflicts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    authoritative_stream_id: Mapped[UUID] = mapped_column(nullable=False)
    witness_stream_id: Mapped[UUID] = mapped_column(nullable=False)
    witness_role: Mapped[str] = mapped_column(String(12), nullable=False, default="cost", server_default="cost")
    authoritative_total_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    witness_total_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    status: Mapped[str] = mapped_column(String(28), nullable=False, default="open", server_default="open")
    detected_run_id: Mapped[UUID] = mapped_column(nullable=False)
    detected_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    resolved_by: Mapped[Optional[UUID]] = mapped_column(_deferred_user_fk())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    resolution_reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','resolved_keep_authoritative','resolved_switch_authority')", name="ck_conflicts_status"
        ),
        CheckConstraint(
            "witness_stream_id <> authoritative_stream_id AND witness_role = 'cost'", name="ck_conflicts_witness"
        ),
        CheckConstraint(
            "(status = 'open') = (resolved_by IS NULL AND resolved_at IS NULL AND resolution_reason IS NULL)",
            name="ck_conflicts_resolution",
        ),
        ForeignKeyConstraint(
            ["team_id", "provider", "billing_account", "usage_account", "usage_date"],
            [
                "cost_source_coverage.team_id",
                "cost_source_coverage.provider",
                "cost_source_coverage.billing_account",
                "cost_source_coverage.usage_account",
                "cost_source_coverage.usage_date",
            ],
            name="fk_conflicts_coverage",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["team_id", "witness_stream_id", "provider", "billing_account", "usage_account", "witness_role"],
            [
                "cost_source_streams.team_id",
                "cost_source_streams.id",
                "cost_source_streams.provider",
                "cost_source_streams.billing_account",
                "cost_source_streams.usage_account",
                "cost_source_streams.role",
            ],
            name="fk_conflicts_witness",
            ondelete="CASCADE",
        ),
        Index(
            "uq_cost_source_conflicts_open",
            "team_id",
            "provider",
            "billing_account",
            "usage_account",
            "usage_date",
            "witness_stream_id",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
        Index(
            "ix_conflicts_witness",
            "team_id",
            "witness_stream_id",
            "provider",
            "billing_account",
            "usage_account",
            "witness_role",
        ),
        Index("ix_conflicts_resolved_by", "resolved_by"),
    )


class CostSourceRecord(Base):
    """Current value of one cost line of one stream and day."""

    __tablename__ = "cost_source_records"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    source_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    dim_1: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default="")
    dim_2: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default="")
    line_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    line_key: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    canonical_service: Mapped[str] = mapped_column(String(256), nullable=False)
    charge_class: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(FX_RATE)
    fx_source: Mapped[Optional[str]] = mapped_column(String(32))
    cost_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    state: Mapped[str] = mapped_column(String(8), nullable=False, default="present", server_default="present")
    absent_since_generation: Mapped[Optional[int]] = mapped_column(BigInteger)
    absent_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    last_generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("length(currency) = 3 AND currency = upper(currency)", name="ck_records_currency"),
        CheckConstraint(f"charge_class IN\n    ({CHARGE_CLASSES},'other')", name="ck_records_charge_class"),
        CheckConstraint(
            "(state = 'present' AND absent_since_generation IS NULL AND absent_at IS NULL)\n"
            "    OR (state = 'absent' AND absent_since_generation IS NOT NULL AND absent_at IS NOT NULL)",
            name="ck_records_state",
        ),
        CheckConstraint(
            "(currency = 'USD' AND amount_usd = amount AND fx_rate IS NULL AND fx_source IS NULL)\n"
            "    OR (currency <> 'USD' AND amount_usd IS NULL AND fx_rate IS NULL AND fx_source IS NULL)\n"
            "    OR (currency <> 'USD' AND amount_usd IS NOT NULL AND fx_rate > 0 AND fx_source IS NOT NULL)",
            name="ck_records_usd",
        ),
        CheckConstraint("canonical_service <> ''", name="ck_records_canonical_service"),
        CheckConstraint("(source_kind = 'manual') = (line_kind LIKE 'manual:%')", name="ck_records_line_kind"),
        CheckConstraint("source_kind = 'provider' OR line_key <> ''", name="ck_records_manual_entry_key"),
        CheckConstraint("last_generation > 0", name="ck_records_generation"),
        UniqueConstraint(
            "team_id",
            "source_kind",
            "stream_id",
            "usage_date",
            "dim_1",
            "dim_2",
            "line_kind",
            "line_key",
            "currency",
            name="uq_cost_source_records_identity",
        ),
        UniqueConstraint("team_id", "id", name="uq_cost_source_records_team_id"),
        ForeignKeyConstraint(
            ["team_id", "stream_id", "source_kind"],
            ["cost_source_streams.team_id", "cost_source_streams.id", "cost_source_streams.source_kind"],
            name="fk_records_stream",
            ondelete="CASCADE",
        ),
        Index(
            "ix_cost_source_records_bucket",
            "team_id",
            "usage_date",
            "cost_bucket",
            postgresql_where=text("state = 'present'"),
            sqlite_where=text("state = 'present'"),
        ),
        Index("ix_cost_source_records_stream_day", "stream_id", "usage_date"),
    )


class CostSourceObservation(Base):
    """Append-only: one row per time a record was observed, by a sync run or a manual actor."""

    __tablename__ = "cost_source_observations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    record_id: Mapped[UUID] = mapped_column(nullable=False)
    sync_run_id: Mapped[Optional[UUID]] = mapped_column()
    connection_id: Mapped[Optional[UUID]] = mapped_column()
    attempt: Mapped[Optional[int]] = mapped_column()
    fencing_token: Mapped[Optional[int]] = mapped_column(BigInteger)
    actor_user_id: Mapped[Optional[UUID]] = mapped_column()
    actor_api_key_id: Mapped[Optional[UUID]] = mapped_column()
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    observed_amount: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    observed_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    observed_amount_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    previous_amount: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    is_estimated: Mapped[bool] = mapped_column(nullable=False)
    payload_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "change_kind IN ('inserted','corrected','unchanged','absent','reappeared','stale_ignored')",
            name="ck_obs_change_kind",
        ),
        CheckConstraint("length(payload_sha256) = 32", name="ck_obs_payload_sha256"),
        CheckConstraint(
            "(sync_run_id IS NOT NULL AND connection_id IS NOT NULL AND attempt IS NOT NULL AND fencing_token IS NOT NULL\n"
            "       AND actor_user_id IS NULL AND actor_api_key_id IS NULL)\n"
            "    OR (sync_run_id IS NULL AND connection_id IS NULL AND attempt IS NULL AND fencing_token IS NULL\n"
            "       AND ((actor_user_id IS NULL) <> (actor_api_key_id IS NULL)))",
            name="ck_obs_actor",
        ),
        CheckConstraint("(change_kind = 'absent') = (observed_amount IS NULL)", name="ck_obs_amount"),
        ForeignKeyConstraint(
            ["team_id", "record_id"],
            ["cost_source_records.team_id", "cost_source_records.id"],
            name="fk_obs_record",
            ondelete="CASCADE",
        ),
        _deferred_fk(
            ["team_id", "connection_id"],
            ["integration_connections.team_id", "integration_connections.id"],
            name="fk_obs_connection",
        ),
        _deferred_fk(
            ["sync_run_id", "connection_id"],
            ["integration_sync_runs.id", "integration_sync_runs.connection_id"],
            name="fk_obs_run",
        ),
        _deferred_fk(["actor_user_id"], ["users.id"], name="fk_obs_user"),
        _deferred_fk(["actor_api_key_id"], ["team_api_keys.id"], name="fk_obs_api_key"),
        Index(
            "uq_cost_source_observations_inserted",
            "record_id",
            unique=True,
            postgresql_where=text("change_kind = 'inserted'"),
            sqlite_where=text("change_kind = 'inserted'"),
        ),
        Index("ix_cost_source_observations_record", "team_id", "record_id", "observed_at"),
        Index("ix_cost_source_observations_run", "sync_run_id", "connection_id"),
        Index("ix_cost_source_observations_connection", "team_id", "connection_id"),
        Index("ix_cost_source_observations_user", "actor_user_id"),
        Index("ix_cost_source_observations_api_key", "actor_api_key_id"),
    )


class BillingCanonicalFact(Base):
    """
    One row per billable expense, keyed only by what the expense is: never by connection, stream,
    run, attempt, vantage, grouping layout or authority. Append-only.
    """

    __tablename__ = "billing_canonical_facts"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    billing_account: Mapped[str] = mapped_column(String(128), nullable=False)
    usage_account: Mapped[str] = mapped_column(String(160), nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    canonical_service: Mapped[str] = mapped_column(String(256), nullable=False)
    charge_class: Mapped[str] = mapped_column(String(16), nullable=False)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    first_record_id: Mapped[UUID] = mapped_column(nullable=False)
    first_run_id: Mapped[Optional[UUID]] = mapped_column()
    registered_in: Mapped[str] = mapped_column(String(10), nullable=False)
    first_billable: Mapped[bool] = mapped_column(nullable=False)
    registered_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint(
            "team_id",
            "provider",
            "billing_account",
            "usage_account",
            "usage_date",
            "canonical_service",
            "charge_class",
            "currency",
        ),
        CheckConstraint("canonical_service <> ''", name="ck_facts_canonical_service"),
        CheckConstraint(f"charge_class IN\n    ({CHARGE_CLASSES})", name="ck_facts_charge_class"),
        CheckConstraint("registered_in IN ('shadow','backfill','live')", name="ck_facts_registered_in"),
        CheckConstraint("NOT first_billable OR registered_in = 'live'", name="ck_facts_billable_only_live"),
        CheckConstraint("NOT first_billable AND registered_in <> 'live'", name="ck_facts_gate_not_billable"),
        _deferred_fk(
            ["team_id", "first_record_id"],
            ["cost_source_records.team_id", "cost_source_records.id"],
            name="fk_facts_first_record",
        ),
        Index("ix_billing_canonical_facts_record", "team_id", "first_record_id"),
    )


class CostSyncLease(Base):
    """Per-connection lease with a fencing token."""

    __tablename__ = "cost_sync_leases"

    connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("integration_connections.id", ondelete="CASCADE"), primary_key=True
    )
    token: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    holder_run_id: Mapped[Optional[UUID]] = mapped_column()
    holder_attempt: Mapped[Optional[int]] = mapped_column()
    expires_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(TZ)

    __table_args__ = (
        CheckConstraint("token >= 0", name="ck_leases_token"),
        CheckConstraint(
            "(holder_run_id IS NULL) = (holder_attempt IS NULL AND expires_at IS NULL)", name="ck_leases_holder"
        ),
        _deferred_fk(
            ["holder_run_id", "connection_id"],
            ["integration_sync_runs.id", "integration_sync_runs.connection_id"],
            name="fk_leases_holder",
        ),
        Index("ix_leases_holder", "holder_run_id", "connection_id"),
    )


class CostSyncRunStream(Base):
    """Progress and completeness of one stream within one run attempt."""

    __tablename__ = "cost_sync_run_streams"

    sync_run_id: Mapped[UUID] = mapped_column(nullable=False)
    connection_id: Mapped[UUID] = mapped_column(nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    pages: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    staged_rows: Mapped[int] = mapped_column(nullable=False, default=0, server_default=text("0"))
    staged_total_usd: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False, default=0, server_default=text("0"))
    provider_total_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("sync_run_id", "attempt", "stream_id"),
        CheckConstraint(
            "status IN ('pending','fetching','complete','published','failed','fenced','stale')",
            name="ck_run_streams_status",
        ),
        CheckConstraint("attempt > 0", name="ck_run_streams_attempt"),
        CheckConstraint("window_end > window_start", name="ck_run_streams_window"),
        ForeignKeyConstraint(
            ["sync_run_id", "connection_id"],
            ["integration_sync_runs.id", "integration_sync_runs.connection_id"],
            name="fk_run_streams_run",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["team_id", "stream_id"],
            ["cost_source_streams.team_id", "cost_source_streams.id"],
            name="fk_run_streams_stream",
            ondelete="CASCADE",
        ),
        _deferred_fk(
            ["team_id", "connection_id"],
            ["integration_connections.team_id", "integration_connections.id"],
            name="fk_run_streams_connection",
        ),
        Index(
            "uq_cost_sync_run_streams_published",
            "sync_run_id",
            "stream_id",
            unique=True,
            postgresql_where=text("status = 'published'"),
            sqlite_where=text("status = 'published'"),
        ),
        Index("ix_run_streams_run", "sync_run_id", "connection_id"),
        Index("ix_run_streams_stream", "team_id", "stream_id"),
        Index("ix_run_streams_connection", "team_id", "connection_id"),
    )


class CostSyncStaging(Base):
    """Fetched pages, staged per run attempt before publication; deleted once published or abandoned."""

    __tablename__ = "cost_sync_staging"

    sync_run_id: Mapped[UUID] = mapped_column(nullable=False)
    attempt: Mapped[int] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    dim_1: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default="")
    dim_2: Mapped[str] = mapped_column(String(256), nullable=False, default="", server_default="")
    line_kind: Mapped[str] = mapped_column(String(48), nullable=False)
    line_key: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    canonical_service: Mapped[str] = mapped_column(String(256), nullable=False)
    charge_class: Mapped[str] = mapped_column(String(16), nullable=False)
    page_seq: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(AMOUNT, nullable=False)
    amount_usd: Mapped[Optional[Decimal]] = mapped_column(AMOUNT)
    fx_rate: Mapped[Optional[Decimal]] = mapped_column(FX_RATE)
    fx_source: Mapped[Optional[str]] = mapped_column(String(32))
    cost_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    is_estimated: Mapped[bool] = mapped_column(nullable=False)
    payload_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint(
            "sync_run_id", "attempt", "stream_id", "usage_date", "dim_1", "dim_2", "line_kind", "line_key", "currency"
        ),
        ForeignKeyConstraint(
            ["sync_run_id", "attempt", "stream_id"],
            ["cost_sync_run_streams.sync_run_id", "cost_sync_run_streams.attempt", "cost_sync_run_streams.stream_id"],
            name="fk_staging_run_stream",
            ondelete="CASCADE",
        ),
    )


class CostSourceStreamCheckpoint(Base):
    """How far each stream is final, and the provider export watermark."""

    __tablename__ = "cost_source_stream_checkpoints"

    team_id: Mapped[UUID] = mapped_column(nullable=False)
    stream_id: Mapped[UUID] = mapped_column(primary_key=True)
    final_through: Mapped[Optional[date]] = mapped_column(Date)
    export_watermark: Mapped[Optional[datetime]] = mapped_column(TZ)
    last_complete_fetch_at: Mapped[Optional[datetime]] = mapped_column(TZ)

    __table_args__ = (
        ForeignKeyConstraint(
            ["team_id", "stream_id"],
            ["cost_source_streams.team_id", "cost_source_streams.id"],
            name="fk_checkpoints_stream",
            ondelete="CASCADE",
        ),
        Index("ix_checkpoints_team_stream", "team_id", "stream_id"),
    )


class CostReconciliationBatch(Base):
    """A reviewed proposal to move legacy totals to ledger totals. Cannot be applied while gated."""

    __tablename__ = "cost_reconciliation_batches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected_inventory: Mapped[list] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    proposed_by: Mapped[UUID] = mapped_column(_deferred_user_fk(), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())
    approved_by: Mapped[Optional[UUID]] = mapped_column(_deferred_user_fk())
    approved_at: Mapped[Optional[datetime]] = mapped_column(TZ)
    approval_reason: Mapped[Optional[str]] = mapped_column(Text)
    retire_legacy_authorized_by: Mapped[Optional[UUID]] = mapped_column(_deferred_user_fk())
    batch_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZ, nullable=False)
    applied_at: Mapped[Optional[datetime]] = mapped_column(TZ)

    __table_args__ = (
        UniqueConstraint("team_id", "id", name="uq_cost_reconciliation_batches_team_id"),
        CheckConstraint(
            "status IN ('proposed','approved','applied','rejected','stale','expired')", name="ck_batches_status"
        ),
        CheckConstraint("date_to >= date_from", name="ck_batches_dates"),
        CheckConstraint("length(batch_fingerprint) = 32", name="ck_batches_fingerprint"),
        CheckConstraint("approved_by IS NULL OR approved_by <> proposed_by", name="ck_batches_four_eyes"),
        CheckConstraint(
            "status NOT IN ('approved','applied') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL "
            "AND approval_reason IS NOT NULL)",
            name="ck_batches_approval",
        ),
        CheckConstraint("(status = 'applied') = (applied_at IS NOT NULL)", name="ck_batches_applied"),
        CheckConstraint("status <> 'applied'", name="ck_batches_gate_no_apply"),
        Index("ix_batches_proposed_by", "proposed_by"),
        Index("ix_batches_approved_by", "approved_by"),
        Index("ix_batches_retire_by", "retire_legacy_authorized_by"),
    )


class CostReconciliationEntry(Base):
    """One legacy total in a batch: old amount, ledger amount, difference, coverage, fingerprint."""

    __tablename__ = "cost_reconciliation_entries"

    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    gpu_type: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(14), nullable=False)
    legacy_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    ledger_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    difference: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 2), Computed("ledger_amount - legacy_amount", persisted=True)
    )
    coverage: Mapped[dict] = mapped_column(JSONB, nullable=False)
    entry_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint("batch_id", "usage_date", "provider", "gpu_type"),
        CheckConstraint(
            "action IN ('replace','retire_legacy') AND (action <> 'retire_legacy' OR ledger_amount = 0)",
            name="ck_entries_action",
        ),
        CheckConstraint("length(entry_fingerprint) = 32", name="ck_entries_fingerprint"),
        ForeignKeyConstraint(
            ["team_id", "batch_id"],
            ["cost_reconciliation_batches.team_id", "cost_reconciliation_batches.id"],
            name="fk_entries_batch",
            ondelete="CASCADE",
        ),
        _deferred_fk(["snapshot_id"], ["cost_snapshots.id"], name="fk_entries_snapshot"),
        Index("ix_entries_snapshot", "snapshot_id"),
        Index("ix_entries_batch", "team_id", "batch_id"),
    )


class CostReconciliationAttempt(Base):
    """Append-only record of every propose/approve/reject/apply attempt, including failed and stale ones."""

    __tablename__ = "cost_reconciliation_attempts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(nullable=False)
    batch_id: Mapped[UUID] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    outcome: Mapped[str] = mapped_column(String(14), nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(_deferred_user_fk(), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    expected_fingerprint: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    actual_fingerprint: Mapped[Optional[bytes]] = mapped_column(LargeBinary)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("action IN ('propose','approve','reject','apply')", name="ck_attempts_action"),
        CheckConstraint(
            "outcome IN ('ok','stale','incomplete','unauthorized','expired','error')", name="ck_attempts_outcome"
        ),
        ForeignKeyConstraint(
            ["team_id", "batch_id"],
            ["cost_reconciliation_batches.team_id", "cost_reconciliation_batches.id"],
            name="fk_attempts_batch",
            ondelete="CASCADE",
        ),
        Index("ix_attempts_batch", "team_id", "batch_id"),
        Index("ix_attempts_actor", "actor_user_id"),
    )


class BillingUsageLedger(Base):
    """Durable billing idempotency (outlives usage_events retention). Shadow-only while gated. Append-only."""

    __tablename__ = "billing_usage_ledger"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    basis: Mapped[str] = mapped_column(String(24), nullable=False)
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    shadow: Mapped[bool] = mapped_column(nullable=False)
    billing_exempt: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=text("false"))
    sync_run_id: Mapped[Optional[UUID]] = mapped_column()
    connection_id: Mapped[Optional[UUID]] = mapped_column()
    stream_id: Mapped[Optional[UUID]] = mapped_column()
    accrual_date: Mapped[date] = mapped_column(Date, nullable=False)
    usage_event_id: Mapped[Optional[UUID]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("basis IN ('legacy_saved_rows','first_ingested')", name="ck_usage_ledger_basis"),
        CheckConstraint("quantity >= 0", name="ck_usage_ledger_quantity"),
        CheckConstraint("NOT (shadow AND usage_event_id IS NOT NULL)", name="ck_usage_ledger_no_event_when_shadow"),
        CheckConstraint(
            "NOT (billing_exempt AND usage_event_id IS NOT NULL)", name="ck_usage_ledger_no_event_when_exempt"
        ),
        CheckConstraint("shadow AND usage_event_id IS NULL", name="ck_usage_ledger_gate_shadow_only"),
        UniqueConstraint("idempotency_key", "basis", name="uq_billing_usage_ledger_key"),
        _deferred_fk(
            ["sync_run_id", "connection_id"],
            ["integration_sync_runs.id", "integration_sync_runs.connection_id"],
            name="fk_usage_ledger_run",
        ),
        _deferred_fk(
            ["team_id", "connection_id"],
            ["integration_connections.team_id", "integration_connections.id"],
            name="fk_usage_ledger_connection",
        ),
        _deferred_fk(
            ["team_id", "stream_id"],
            ["cost_source_streams.team_id", "cost_source_streams.id"],
            name="fk_usage_ledger_stream",
        ),
        Index("ix_usage_ledger_run", "sync_run_id", "connection_id"),
        Index("ix_usage_ledger_connection", "team_id", "connection_id"),
        Index("ix_usage_ledger_stream", "team_id", "stream_id"),
    )


class ManualCostRequest(Base):
    """Stored response of a manual cost request, replayed for the same Idempotency-Key."""

    __tablename__ = "manual_cost_requests"

    team_id: Mapped[UUID] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    response_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSONB, nullable=False)
    actor_user_id: Mapped[Optional[UUID]] = mapped_column(_deferred_user_fk())
    actor_api_key_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("team_api_keys.id", deferrable=True, initially="DEFERRED")
    )
    created_at: Mapped[datetime] = mapped_column(TZ, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("team_id", "idempotency_key"),
        CheckConstraint("(actor_user_id IS NULL) <> (actor_api_key_id IS NULL)", name="ck_manual_requests_actor"),
        Index("ix_manual_requests_user", "actor_user_id"),
        Index("ix_manual_requests_api_key", "actor_api_key_id"),
    )


# ── PostgreSQL-only objects: same SQL as migration 038 ───────────────────────────


def _pg_ddl(sql: str) -> DDL:
    # DDL() applies %-formatting while the migration executes the SQL verbatim, so escape here
    return DDL(sql.replace("%", "%%")).execute_if(dialect="postgresql")


event.listen(Base.metadata, "before_create", _pg_ddl(GUARD_FUNCTION_V1))
event.listen(Base.metadata, "before_create", _pg_ddl(RECORD_DELETE_GUARD_FUNCTION_V1))
for _table_name in GUARDED_TABLES_V1:
    event.listen(Base.metadata.tables[_table_name], "after_create", _pg_ddl(guard_trigger_v1(_table_name)))
event.listen(CostSourceRecord.__table__, "after_create", _pg_ddl(RECORD_DELETE_TRIGGER_V1))
event.listen(Base.metadata, "after_drop", _pg_ddl("DROP FUNCTION IF EXISTS cost_audit_guard()"))
event.listen(Base.metadata, "after_drop", _pg_ddl("DROP FUNCTION IF EXISTS cost_record_delete_guard()"))
