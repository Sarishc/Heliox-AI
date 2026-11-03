"""
Migration 038 and the SQLAlchemy models produce the same PostgreSQL schema.

Database A: ``alembic upgrade head`` from an empty database (base through 038).
Database B: ``Base.metadata.create_all()``, which also runs the PostgreSQL-only DDL hooks
(trigger functions and triggers from app.models.cost_ledger_ddl).

Compared for every table 038 creates or alters: table kind, columns (type, NOT NULL, default,
generated), primary keys, unique/check/foreign-key constraints (definitions and deferrability),
indexes (including predicates), triggers, trigger functions, object dependencies; and every enum
type in the schema. The only intentionally migration-only object is Alembic's own
``alembic_version`` table. Negative controls alter database B and require a reported difference.
"""

import pytest
from postgres_scratch import BACKEND, alembic, needs_postgres, scratch_database
from sqlalchemy import create_engine, text

from app.models import Base
from app.models.cost_ledger_ddl import GUARDED_TABLES_V1

pytestmark = needs_postgres
MIGRATION_038 = BACKEND / "alembic" / "versions" / "038_cost_source_ledger.py"

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
ALTERED_TABLES = ["cost_snapshots", "integration_connections", "integration_sync_runs"]
COMPARED = NEW_TABLES + ALTERED_TABLES
MIGRATION_ONLY = {("table", "alembic_version")}

FINGERPRINT_SQL = """
SELECT 'table', c.relname, c.relkind::text || ' persistence=' || c.relpersistence::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm')
UNION ALL
SELECT 'column', c.relname || '.' || a.attname,
       format_type(a.atttypid, a.atttypmod) || ' notnull=' || a.attnotnull || ' generated=' || a.attgenerated::text
       || ' default=' || coalesce(pg_get_expr(d.adbin, d.adrelid), '-')
  FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid
  LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
 WHERE c.relname = ANY(:tables) AND a.attnum > 0 AND NOT a.attisdropped
UNION ALL
SELECT 'constraint', conrelid::regclass::text || '.' || conname,
       contype::text || ' ' || pg_get_constraintdef(oid) || ' deferrable=' || condeferrable || ' deferred=' || condeferred
       || ' validated=' || convalidated
  FROM pg_constraint WHERE conrelid::regclass::text = ANY(:tables)
UNION ALL
SELECT 'index', tablename || '.' || indexname, indexdef FROM pg_indexes WHERE tablename = ANY(:tables)
UNION ALL
SELECT 'trigger', tgrelid::regclass::text || '.' || tgname, pg_get_triggerdef(oid) || ' enabled=' || tgenabled::text
  FROM pg_trigger WHERE tgrelid::regclass::text = ANY(:tables) AND NOT tgisinternal
UNION ALL
SELECT 'function', p.proname, md5(pg_get_functiondef(p.oid)) || ' secdef=' || p.prosecdef
  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
 WHERE n.nspname = 'public' AND p.prorettype = 'trigger'::regtype
UNION ALL
SELECT 'enum', t.typname, string_agg(e.enumlabel, ',' ORDER BY e.enumsortorder)
  FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid GROUP BY t.typname
UNION ALL
SELECT 'dependency', 'trigger ' || tgrelid::regclass::text || '.' || tgname, 'function ' || tgfoid::regproc::text
  FROM pg_trigger WHERE tgrelid::regclass::text = ANY(:tables) AND NOT tgisinternal
UNION ALL
SELECT 'dependency', 'constraint ' || conrelid::regclass::text || '.' || conname,
       'table ' || coalesce(confrelid::regclass::text, '-') || ' index ' || coalesce(nullif(conindid, 0)::regclass::text, '-')
  FROM pg_constraint WHERE conrelid::regclass::text = ANY(:tables) AND contype IN ('f', 'u', 'p')
"""


def fingerprint(conn) -> dict:
    rows = conn.execute(text(FINGERPRINT_SQL), {"tables": COMPARED}).all()
    return {(kind, name): definition for kind, name, definition in rows}


# Differences that existed before 038, in objects 038 does not create or change: the old columns and
# indexes of the three altered tables, and enum types of other tables (models that use non-native
# enums, and integrationprovider's label order after a later ALTER TYPE ... ADD VALUE). Pinned with
# both values, so any change to them, or any new difference, still fails. Fixing them is out of
# scope for 038; test_migration_038_preservation_postgres proves 038 leaves them untouched.
_TS, _TSTZ = "timestamp without time zone", "timestamp with time zone"
PRE_EXISTING_DRIFT = {
    ("column", "cost_snapshots.created_at"): (
        f"{_TS} notnull=true generated= default=now()",
        f"{_TSTZ} notnull=true generated= default=now()",
    ),
    ("column", "cost_snapshots.updated_at"): (
        f"{_TS} notnull=true generated= default=now()",
        f"{_TSTZ} notnull=true generated= default=now()",
    ),
    ("column", "cost_snapshots.team_id"): (
        "uuid notnull=false generated= default=-",
        "uuid notnull=true generated= default=-",
    ),
    ("constraint", "cost_snapshots.fk_cost_snapshots_team_id_teams"): (
        "f FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE deferrable=false deferred=false validated=true",
        None,
    ),
    ("constraint", "cost_snapshots.cost_snapshots_team_id_fkey"): (
        None,
        "f FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE deferrable=false deferred=false validated=true",
    ),
    ("dependency", "constraint cost_snapshots.fk_cost_snapshots_team_id_teams"): ("table teams index teams_pkey", None),
    ("dependency", "constraint cost_snapshots.cost_snapshots_team_id_fkey"): (None, "table teams index teams_pkey"),
    ("index", "cost_snapshots.ix_cost_snapshots_team_date_desc"): (
        "CREATE INDEX ix_cost_snapshots_team_date_desc ON public.cost_snapshots USING btree (team_id, date DESC)",
        None,
    ),
    ("index", "cost_snapshots.ix_cost_snapshots_team_id_id"): (
        "CREATE INDEX ix_cost_snapshots_team_id_id ON public.cost_snapshots USING btree (team_id, id)",
        None,
    ),
    ("column", "integration_connections.auto_sync_enabled"): (
        "boolean notnull=true generated= default=true",
        "boolean notnull=true generated= default=-",
    ),
    ("column", "integration_connections.created_at"): (
        f"{_TSTZ} notnull=true generated= default=now()",
        f"{_TSTZ} notnull=true generated= default=-",
    ),
    ("column", "integration_connections.updated_at"): (
        f"{_TSTZ} notnull=true generated= default=now()",
        f"{_TSTZ} notnull=true generated= default=-",
    ),
    ("column", "integration_connections.status"): (
        "integrationstatus notnull=true generated= default='pending'::integrationstatus",
        "integrationstatus notnull=true generated= default=-",
    ),
    ("column", "integration_connections.sync_interval_minutes"): (
        "integer notnull=true generated= default=60",
        "integer notnull=true generated= default=-",
    ),
    ("column", "integration_sync_runs.error_details"): (
        "jsonb notnull=false generated= default=-",
        "json notnull=false generated= default=-",
    ),
    ("column", "integration_sync_runs.metrics_json"): (
        "jsonb notnull=false generated= default=-",
        "json notnull=false generated= default=-",
    ),
    ("column", "integration_sync_runs.status"): (
        "syncstatus notnull=true generated= default='running'::syncstatus",
        "syncstatus notnull=true generated= default=-",
    ),
    ("column", "integration_sync_runs.triggered_by"): (
        "character varying(50) notnull=true generated= default='manual'::character varying",
        "character varying(50) notnull=true generated= default=-",
    ),
    ("enum", "integrationprovider"): (
        "aws,gcp,azure,stripe,sso_google,sso_okta,slack,custom,gcp_billing_bigquery",
        "aws,gcp,gcp_billing_bigquery,azure,stripe,sso_google,sso_okta,slack,custom",
    ),
    ("enum", "billingplan"): ("free,starter,growth,enterprise", None),
    ("enum", "oauthprovider"): ("google,github,microsoft,okta", None),
    ("enum", "subscriptionstatus"): ("active,trialing,past_due,canceled,unpaid,incomplete,incomplete_expired", None),
    ("enum", "usageeventtype"): ("api_request,ingestion,seat,gpu_node", None),
}


def differences(a: dict, b: dict) -> list[str]:
    """Every difference that is neither migration-only nor exactly the pinned pre-existing drift."""
    out = []
    for key in sorted(set(a) | set(b)):
        if key in MIGRATION_ONLY or a.get(key) == b.get(key):
            continue
        if PRE_EXISTING_DRIFT.get(key) == (a.get(key), b.get(key)):
            continue
        out.append(f"{key}: alembic={a.get(key)!r} metadata={b.get(key)!r}")
    return out


@pytest.fixture(scope="module")
def schemas():
    with scratch_database("heliox_parity_alembic") as url_a, scratch_database("heliox_parity_metadata") as url_b:
        alembic(url_a, "upgrade", "head")
        engine_a, engine_b = create_engine(url_a), create_engine(url_b)
        Base.metadata.create_all(engine_b)
        with engine_a.connect() as conn:
            fa = fingerprint(conn)
        with engine_b.connect() as conn:
            fb = fingerprint(conn)
        yield {"a": fa, "b": fb, "engine_b": engine_b}
        engine_a.dispose()
        engine_b.dispose()


def test_alembic_and_metadata_produce_identical_ledger_schema(schemas):
    assert differences(schemas["a"], schemas["b"]) == []


def test_comparison_covers_every_new_and_altered_object(schemas):
    fa = schemas["a"]
    counts = {}
    for kind, _ in fa:
        counts[kind] = counts.get(kind, 0) + 1
    tables = {name for kind, name in fa if kind == "table"}
    assert set(COMPARED) <= tables
    # Floors so a broken fingerprint query cannot pass vacuously
    assert counts["column"] >= 280
    assert counts["constraint"] >= 150
    assert counts["index"] >= 60
    assert counts["trigger"] == len(GUARDED_TABLES_V1) + 1
    assert {name for kind, name in fa if kind == "function"} >= {"cost_audit_guard", "cost_record_delete_guard"}
    assert counts["enum"] >= 5


def test_only_alembic_version_is_migration_only(schemas):
    pinned_only_in_a = {k for k, (a, b) in PRE_EXISTING_DRIFT.items() if b is None}
    only_a = set(schemas["a"]) - set(schemas["b"]) - pinned_only_in_a
    assert only_a == MIGRATION_ONLY


def test_pre_existing_drift_is_exactly_the_documented_set(schemas):
    fa, fb = schemas["a"], schemas["b"]
    actual = {
        k: (fa.get(k), fb.get(k)) for k in set(fa) | set(fb) if fa.get(k) != fb.get(k) and k not in MIGRATION_ONLY
    }
    assert actual == PRE_EXISTING_DRIFT


def test_no_pre_existing_drift_touches_a_038_object():
    for kind, name in PRE_EXISTING_DRIFT:
        if kind == "enum":
            continue
        table = name.split(" ")[-1].split(".")[0]
        assert table in ALTERED_TABLES, (kind, name)
        assert not any(
            added in name
            for added in (
                "source_mode",
                "completeness",
                "unconverted_count",
                "ledger_updated_at",
                "deleted_at",
                "phase",
                "pipeline",
                "lease",
                "uq_",
                "ck_",
            )
        )


NEGATIVE_CONTROLS = {
    "drop a gate constraint": "ALTER TABLE team_cost_ledger_settings DROP CONSTRAINT ck_ledger_settings_gate_no_live",
    "drop an index": "DROP INDEX ix_cost_source_records_stream_day",
    "change a partial index predicate": (
        "DROP INDEX uq_sync_runs_inflight; CREATE UNIQUE INDEX uq_sync_runs_inflight ON integration_sync_runs "
        "(connection_id) WHERE phase IN ('queued','leased')"
    ),
    "drop a trigger": "DROP TRIGGER trg_cost_source_observations_guard ON cost_source_observations",
    "alter a column type": "ALTER TABLE cost_source_records ALTER COLUMN amount TYPE numeric(24,9)",
    "make a foreign key non-deferrable": "ALTER TABLE cost_source_observations ALTER CONSTRAINT fk_obs_connection NOT DEFERRABLE",
    "add an enum value": "ALTER TYPE syncstatus ADD VALUE 'drifted'",
    "replace a trigger function": (
        "CREATE OR REPLACE FUNCTION cost_record_delete_guard() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN OLD; END'"
    ),
}


@pytest.mark.parametrize("statement", NEGATIVE_CONTROLS.values(), ids=NEGATIVE_CONTROLS.keys())
def test_negative_control_detects_drift(schemas, statement):
    engine_b = schemas["engine_b"]
    conn = engine_b.connect()
    tx = conn.begin()
    try:
        conn.exec_driver_sql(statement.replace("%", "%%"))
        drifted = fingerprint(conn)
    finally:
        tx.rollback()
        conn.close()
    assert differences(schemas["a"], drifted), f"drift not detected: {statement}"
    with engine_b.connect() as check:
        assert differences(schemas["a"], fingerprint(check)) == [], "negative control leaked"


def test_shared_trigger_sql_is_used_by_both_paths(schemas):
    digest = {k: v for k, v in schemas["a"].items() if k[0] == "function"}
    assert digest == {k: v for k, v in schemas["b"].items() if k[0] == "function"}
    # And the migration imports the shared constants rather than keeping its own copy
    source = MIGRATION_038.read_text()
    assert "from app.models.cost_ledger_ddl import" in source
    assert "CREATE FUNCTION" not in source
