"""
The cost ledger models (migration 038) keep SQLite create_all() working for the unit tests.

Runs on the shared SQLite schema from conftest: every ledger table exists, partial indexes keep their
predicates, existing rows get the legacy defaults, and the portable CHECK constraints (gates included)
are enforced on SQLite too.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.integrations.models import IntegrationConnection, IntegrationSyncRun
from app.models import Base, CostSnapshot, Team, TeamCostLedgerSettings

LEDGER_TABLES = {
    "team_cost_ledger_settings",
    "cost_source_streams",
    "cost_source_stream_bindings",
    "cost_source_authority",
    "cost_source_authority_history",
    "cost_source_stream_days",
    "cost_source_coverage",
    "cost_source_conflicts",
    "cost_source_records",
    "cost_source_observations",
    "billing_canonical_facts",
    "cost_sync_leases",
    "cost_sync_run_streams",
    "cost_sync_staging",
    "cost_source_stream_checkpoints",
    "cost_reconciliation_batches",
    "cost_reconciliation_entries",
    "cost_reconciliation_attempts",
    "billing_usage_ledger",
    "manual_cost_requests",
}


def test_all_ledger_tables_are_created(db_engine):
    assert LEDGER_TABLES <= set(inspect(db_engine).get_table_names())
    assert LEDGER_TABLES <= set(Base.metadata.tables)


def test_partial_indexes_keep_their_predicates(db_engine):
    with db_engine.connect() as conn:
        rows = dict(
            conn.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'index' AND sql LIKE '%WHERE%'")).all()
        )
    assert "WHERE phase IN ('queued','leased','fetching','publishing')" in rows["uq_sync_runs_inflight"]
    assert "WHERE change_kind = 'inserted'" in rows["uq_cost_source_observations_inserted"]
    assert "WHERE status = 'published'" in rows["uq_cost_sync_run_streams_published"]


def _team(db):
    team = Team(name=f"ledger-sqlite-{uuid.uuid4().hex[:8]}")
    db.add(team)
    db.flush()
    return team


def test_existing_rows_get_legacy_defaults(db_session):
    team = _team(db_session)
    snapshot = CostSnapshot(
        team_id=team.id, date=date(2026, 10, 1), provider="aws", gpu_type="ec2", cost_usd=Decimal("250.00")
    )
    connection = IntegrationConnection(team_id=team.id, provider="aws", name="aws", config_encrypted="x")
    db_session.add_all([snapshot, connection])
    db_session.flush()
    run = IntegrationSyncRun(connection_id=connection.id, started_at=snapshot.created_at)
    db_session.add(run)
    db_session.flush()
    db_session.refresh(snapshot)
    db_session.refresh(run)
    assert (snapshot.source_mode, snapshot.completeness, snapshot.unconverted_count) == ("legacy", "legacy", 0)
    assert (run.pipeline, run.phase, run.attempt, run.billing_exempt) == ("legacy", None, 0, False)
    assert connection.deleted_at is None


def test_gates_are_enforced_on_sqlite(db_session):
    team = _team(db_session)
    with pytest.raises(IntegrityError, match="ck_ledger_settings_gate_no_live"):
        with db_session.begin_nested():
            db_session.add(TeamCostLedgerSettings(team_id=team.id, ledger_mode="live"))
            db_session.flush()
    with pytest.raises(IntegrityError, match="ck_cost_snapshots"):
        with db_session.begin_nested():
            db_session.add(
                CostSnapshot(
                    team_id=team.id,
                    date=date(2026, 10, 2),
                    provider="aws",
                    gpu_type="ec2",
                    cost_usd=Decimal("1"),
                    source_mode="ledger",
                    completeness="complete",
                )
            )
            db_session.flush()
