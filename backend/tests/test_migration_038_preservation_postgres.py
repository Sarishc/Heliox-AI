"""
Migration 038 preserves every existing row and refuses to destroy ledger data, on real PostgreSQL.

A database is migrated to 037 and filled with realistic data (two tenants, historical and manual cost
snapshots, connections, sync runs including stuck RUNNING ones, usage events, daily rollups, Stripe
meter exports). Checksums of every row (over the 037 columns), counts and money totals are taken
before 038 and compared after upgrade, after an untouched downgrade, and after re-upgrade.
Downgrade is then refused once any ledger or audit data exists. Also checks that 038 rolls back
completely when it fails, and that it runs as an ordinary owner role (no superuser, no role creation).
"""

import re
import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from postgres_scratch import (
    BACKEND,
    SERVER_URL,
    alembic,
    alembic_version,
    needs_postgres,
    run_alembic,
    scratch_database,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

pytestmark = needs_postgres

MIGRATION_038 = BACKEND / "alembic" / "versions" / "038_cost_source_ledger.py"
PRESERVED = [
    "teams",
    "users",
    "cost_snapshots",
    "integration_connections",
    "integration_sync_runs",
    "usage_events",
    "usage_daily_rollups",
    "stripe_meter_exports",
]
NEW_TABLES = [
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
]
T1, T2 = "a0000000-0000-0000-0000-00000000000a", "b0000000-0000-0000-0000-00000000000b"
C1, C2, C3 = (f"c{i}000000-0000-0000-0000-00000000000{i}" for i in (1, 2, 3))

FIXTURE_037 = f"""
INSERT INTO teams (id, name) VALUES ('{T1}', 'Acme Robotics'), ('{T2}', 'Birch Labs');
INSERT INTO users (id, email, hashed_password) VALUES
  ('a1000000-0000-0000-0000-000000000001', 'alice@acme.test', 'x');
INSERT INTO cost_snapshots (id, team_id, date, provider, gpu_type, cost_usd) VALUES
  ('e1000000-0000-0000-0000-000000000001', '{T1}', '2026-09-30', 'aws', 'ec2', 250.00),
  ('e1000000-0000-0000-0000-000000000002', '{T1}', '2026-10-01', 'aws', 'ec2', 1234.56),
  ('e1000000-0000-0000-0000-000000000003', '{T1}', '2026-10-01', 'gcp', 'compute-engine', 0.01),
  ('e1000000-0000-0000-0000-000000000004', '{T1}', '2026-10-02', 'onprem', 'a100', 4999.99),
  ('e1000000-0000-0000-0000-000000000005', '{T2}', '2026-10-01', 'aws', 'ec2', 100.00),
  ('e1000000-0000-0000-0000-000000000006', '{T2}', '2025-01-15', 'azure', 'azure_vm', 87654.32);
INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted, status) VALUES
  ('{C1}', '{T1}', 'aws', 'Acme AWS', 'enc', 'active'),
  ('{C2}', '{T1}', 'gcp_billing_bigquery', 'Acme GCP', 'enc', 'error'),
  ('{C3}', '{T2}', 'azure', 'Birch Azure', 'enc', 'active');
INSERT INTO integration_sync_runs (id, connection_id, started_at, finished_at, status, triggered_by, metrics_json) VALUES
  ('d1000000-0000-0000-0000-000000000001', '{C1}', '2026-10-01 01:00Z', '2026-10-01 01:02Z', 'success', 'scheduled', '{{"records_saved": 4}}'),
  ('d1000000-0000-0000-0000-000000000002', '{C1}', '2026-10-02 01:00Z', NULL, 'running', 'scheduled', NULL),
  ('d1000000-0000-0000-0000-000000000003', '{C1}', '2026-10-03 01:00Z', NULL, 'running', 'manual', NULL),
  ('d1000000-0000-0000-0000-000000000004', '{C2}', '2026-10-01 02:00Z', '2026-10-01 02:01Z', 'failed', 'manual', NULL);
INSERT INTO usage_events (id, team_id, event_type, quantity, metadata, created_at, updated_at) VALUES
  ('f1000000-0000-0000-0000-000000000001', '{T1}', 'ingestion', 4, '{{"source": "aws"}}', '2026-10-01 01:02Z', '2026-10-01 01:02Z'),
  ('f1000000-0000-0000-0000-000000000002', '{T1}', 'api_request', 17, '{{}}', '2026-10-01 05:00Z', '2026-10-01 05:00Z'),
  ('f1000000-0000-0000-0000-000000000003', '{T2}', 'ingestion', 9, '{{"source": "azure"}}', '2026-10-01 07:00Z', '2026-10-01 07:00Z');
INSERT INTO usage_daily_rollups (id, team_id, date, event_type, total_quantity) VALUES
  ('f2000000-0000-0000-0000-000000000001', '{T1}', '2026-10-01', 'ingestion', 4),
  ('f2000000-0000-0000-0000-000000000002', '{T2}', '2026-10-01', 'ingestion', 9);
INSERT INTO stripe_meter_exports (id, team_id, export_date, event_type, quantity, stripe_identifier, status) VALUES
  ('f3000000-0000-0000-0000-000000000001', '{T1}', '2026-10-01', 'ingestion', 4, 'heliox_{T1}_2026-10-01_ingestion', 'succeeded'),
  ('f3000000-0000-0000-0000-000000000002', '{T2}', '2026-10-01', 'ingestion', 9, 'heliox_{T2}_2026-10-01_ingestion', 'failed');
"""


def _columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        text("SELECT column_name FROM information_schema.columns WHERE table_name = :t ORDER BY ordinal_position"),
        {"t": table},
    )
    return [r[0] for r in rows]


def snapshot(engine, columns: dict | None = None) -> dict:
    """Row checksums over the given (037) columns, row counts and money totals."""
    out = {}
    with engine.connect() as conn:
        cols = columns or {t: _columns(conn, t) for t in PRESERVED}
        for table in PRESERVED:
            row = ", ".join(f"coalesce({c}::text, '<null>')" for c in cols[table])
            out[table] = conn.execute(
                text(
                    f"SELECT count(*), md5(coalesce(string_agg(concat_ws('|', {row}), ',' ORDER BY id::text), '')) FROM {table}"
                )
            ).one()
        out["cost_total"] = conn.execute(text("SELECT sum(cost_usd) FROM cost_snapshots")).scalar()
        out["usage_total"] = conn.execute(text("SELECT sum(quantity) FROM usage_events")).scalar()
        out["export_total"] = conn.execute(text("SELECT sum(quantity) FROM stripe_meter_exports")).scalar()
    return out, cols


@pytest.fixture
def db_037():
    with scratch_database("heliox_mig038") as url:
        alembic(url, "upgrade", "037")
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text(FIXTURE_037))
        yield url, engine
        engine.dispose()


def _new_tables_present(engine) -> list[str]:
    with engine.connect() as conn:
        return [t for t in NEW_TABLES if conn.execute(text("SELECT to_regclass(:t)"), {"t": t}).scalar()]


def test_history_has_one_head_and_038_follows_037():
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    script = ScriptDirectory.from_config(cfg)
    assert script.get_heads() == ["038"]
    assert script.get_revision("038").down_revision == "037"


def test_upgrade_preserves_every_row_and_total(db_037):
    url, engine = db_037
    before, cols = snapshot(engine)
    alembic(url, "upgrade", "head")
    after, _ = snapshot(engine, cols)
    assert alembic_version(engine) == ["038"]
    assert after == before
    assert str(before["cost_total"]) == "94238.88"
    with engine.connect() as conn:
        # every team is off (no settings row); nothing new exists or was generated
        for table in NEW_TABLES:
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar() == 0, table
        assert (
            conn.execute(
                text("SELECT count(*) FROM cost_snapshots WHERE source_mode <> 'legacy' OR completeness <> 'legacy'")
            ).scalar()
            == 0
        )
        legacy_runs = conn.execute(
            text("SELECT count(*) FROM integration_sync_runs WHERE pipeline = 'legacy' AND phase IS NULL")
        ).scalar()
        assert legacy_runs == 4
        assert conn.execute(text("SELECT count(*) FROM integration_sync_runs WHERE status = 'running'")).scalar() == 2


def test_upgrade_leaves_pre_existing_objects_of_altered_tables_untouched(db_037):
    from test_migration_038_parity_postgres import fingerprint

    url, engine = db_037
    with engine.connect() as conn:
        before = fingerprint(conn)
    alembic(url, "upgrade", "head")
    with engine.connect() as conn:
        after = fingerprint(conn)
    assert {k: after.get(k) for k in before} == before


def test_untouched_downgrade_restores_037_exactly(db_037):
    from test_migration_038_parity_postgres import fingerprint

    url, engine = db_037
    before, cols = snapshot(engine)
    with engine.connect() as conn:
        schema_037 = fingerprint(conn)
    alembic(url, "upgrade", "head")
    alembic(url, "downgrade", "037")
    assert alembic_version(engine) == ["037"]
    assert _new_tables_present(engine) == []
    with engine.connect() as conn:
        assert fingerprint(conn) == schema_037
    assert snapshot(engine, cols)[0] == before
    alembic(url, "upgrade", "head")
    assert alembic_version(engine) == ["038"]
    assert snapshot(engine, cols)[0] == before


LEDGER_DATA = {
    "a shadow settings row": f"INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T1}', 'shadow')",
    "a soft-deleted connection": f"UPDATE integration_connections SET deleted_at = now() WHERE id = '{C3}'",
    "a ledger sync run": (
        "INSERT INTO integration_sync_runs (id, connection_id, started_at, status, triggered_by, pipeline, phase, dispatch_deadline_at) "
        f"VALUES (gen_random_uuid(), '{C2}', now(), 'running', 'scheduled', 'ledger', 'queued', now())"
    ),
    "an audit observation": (
        "INSERT INTO cost_source_streams (id, team_id, source_kind, role, provider, scope_type, usage_account, vantage, metric, "
        f"grouping_version, config_sha256) VALUES ('5a000000-0000-0000-0000-00000000000a', '{T1}', 'manual', 'cost', 'aws', 'manual', "
        "'manual:api', 'manual:api', 'manual:amount', 'manual.v1', sha256('m'));"
        "INSERT INTO cost_source_records (id, team_id, stream_id, source_kind, usage_date, dim_1, line_kind, line_key, currency, "
        "canonical_service, charge_class, amount, amount_usd, cost_bucket, last_generation) VALUES "
        f"('5b000000-0000-0000-0000-00000000000b', '{T1}', '5a000000-0000-0000-0000-00000000000a', 'manual', '2026-10-05', 'ec2', "
        "'manual:charge', 'default', 'USD', 'ec2', 'usage', 1, 1, 'ec2', 1);"
        "INSERT INTO cost_source_observations (id, team_id, record_id, actor_user_id, generation, change_kind, observed_amount, "
        f"observed_currency, is_estimated, payload_sha256) VALUES (gen_random_uuid(), '{T1}', '5b000000-0000-0000-0000-00000000000b', "
        "'a1000000-0000-0000-0000-000000000001', 1, 'inserted', 1, 'USD', false, sha256('o'))"
    ),
}


@pytest.mark.parametrize("statement", LEDGER_DATA.values(), ids=LEDGER_DATA.keys())
def test_downgrade_refuses_to_destroy_ledger_data(db_037, statement):
    url, engine = db_037
    alembic(url, "upgrade", "head")
    with engine.begin() as conn:
        conn.exec_driver_sql(statement)
    before, cols = snapshot(engine)
    result = run_alembic(url, "downgrade", "037")
    assert result.returncode != 0
    assert "038 downgrade refused, it would destroy ledger or audit data" in result.stderr
    assert alembic_version(engine) == ["038"]
    assert _new_tables_present(engine) == NEW_TABLES
    assert snapshot(engine, cols)[0] == before


def test_failed_upgrade_rolls_back_completely(db_037):
    url, engine = db_037
    before, cols = snapshot(engine)
    # An index name 038 creates near its end already exists: the upgrade fails after most DDL ran
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE blocker (x int); CREATE INDEX ix_usage_ledger_stream ON blocker (x)"))
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode != 0
    assert 'relation "ix_usage_ledger_stream" already exists' in result.stderr
    assert alembic_version(engine) == ["037"]
    assert _new_tables_present(engine) == []
    with engine.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns WHERE table_name = 'cost_snapshots' AND column_name = 'source_mode'"
                )
            ).scalar()
            == 0
        )
        assert conn.execute(text("SELECT count(*) FROM pg_proc WHERE proname = 'cost_audit_guard'")).scalar() == 0
    assert snapshot(engine, cols)[0] == before


def test_upgrade_refuses_a_schema_that_already_has_ledger_objects(db_037):
    url, engine = db_037
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE cost_source_streams (id uuid)"))
    result = run_alembic(url, "upgrade", "head")
    assert result.returncode != 0
    assert "038 refused: schema is not what 037 left" in result.stderr
    assert alembic_version(engine) == ["037"]


def test_live_pathways_are_rejected_right_after_upgrade(db_037):
    url, engine = db_037
    alembic(url, "upgrade", "head")
    for statement, constraint in (
        (
            f"INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T1}', 'live')",
            "ck_ledger_settings_gate_no_live",
        ),
        (
            "UPDATE cost_snapshots SET source_mode = 'ledger', completeness = 'complete', ledger_updated_at = now()",
            "ck_cost_snapshots_gate_legacy_only",
        ),
    ):
        with pytest.raises(IntegrityError, match=constraint):
            with engine.begin() as conn:
                conn.execute(text(statement))


def test_migration_source_creates_no_cluster_objects():
    source = MIGRATION_038.read_text().split('"""', 2)[2]  # code only: the docstring names what 038 avoids
    for forbidden in (
        "CREATE ROLE",
        "GRANT ",
        "REVOKE ",
        "OWNER TO",
        "SECURITY DEFINER",
        "CREATE EXTENSION",
        "ALTER SYSTEM",
        "CONCURRENTLY",
        "session_replication_role",
    ):
        assert forbidden not in source, forbidden
    assert not re.search(r"\bpassword\b", source, re.IGNORECASE)


def test_full_history_runs_as_an_ordinary_owner_role():
    """No superuser and no role creation needed: the whole history, 038 included, runs as a plain database owner."""
    role, password = f"heliox_owner_{uuid.uuid4().hex[:10]}", uuid.uuid4().hex
    database = f"heliox_mig038_owner_{uuid.uuid4().hex[:10]}"
    admin = create_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(
            text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION")
        )
        conn.execute(text(f'CREATE DATABASE "{database}" OWNER {role}'))
    try:
        url = (
            make_url(SERVER_URL)
            .set(database=database, username=role, password=password)
            .render_as_string(hide_password=False)
        )
        alembic(url, "upgrade", "head")
        engine = create_engine(url)
        assert alembic_version(engine) == ["038"]
        with engine.connect() as conn:
            roles_after = conn.execute(
                text("SELECT count(*) FROM pg_roles WHERE rolname LIKE 'heliox_audit%'")
            ).scalar()
            owners = {
                r[0]
                for r in conn.execute(text("SELECT DISTINCT tableowner FROM pg_tables WHERE schemaname = 'public'"))
            }
        engine.dispose()
        assert roles_after == 0
        assert owners == {role}
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
            conn.execute(text(f"DROP ROLE IF EXISTS {role}"))
        admin.dispose()
