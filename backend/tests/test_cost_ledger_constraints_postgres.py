"""
Database-level guarantees of the cost ledger schema (migration 038), on real PostgreSQL.

- Live mode is impossible: every attempt fails on its named gate constraint.
- Financial identity: one billing fact per real expense, whatever observes it; distinct charges stay
  distinct; tenants never share or cross-reference rows.
- Privileges: a restricted application role (disposable, created only for this test) can append audit
  rows but cannot change or delete them, disable or drop triggers, skip triggers or change the schema.
  The table owner and superusers CAN bypass the guards; that limit is asserted, not hidden.
- Nothing in the application (scheduler, routes, Stripe exporter) touches the new tables yet.
"""

import re
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from postgres_scratch import alembic, needs_postgres, scratch_database
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

pytestmark = needs_postgres

APP_DIR = Path(__file__).resolve().parents[1] / "app"
T1, T2 = "a0000000-0000-0000-0000-00000000000a", "b0000000-0000-0000-0000-00000000000b"
ALICE, BOB = "a1000000-0000-0000-0000-000000000001", "a2000000-0000-0000-0000-000000000002"
C1, C2, C3 = (
    "c1000000-0000-0000-0000-000000000001",
    "c2000000-0000-0000-0000-000000000002",
    "c3000000-0000-0000-0000-000000000003",
)
PAYER, MEMBER, PAYER_V2, TAGS, BIRCH, MANUAL = (
    "51000000-0000-0000-0000-000000000001",
    "52000000-0000-0000-0000-000000000002",
    "51200000-0000-0000-0000-000000000012",
    "51700000-0000-0000-0000-000000000017",
    "56000000-0000-0000-0000-000000000006",
    "5a000000-0000-0000-0000-00000000000a",
)


def _stream(
    sid,
    team,
    vantage,
    version="aws.v1.service+record_type",
    role="cost",
    kind="provider",
    account="aws:acct:111122223333",
):
    scope = "manual" if kind == "manual" else "aws:linked_account"
    return (
        "INSERT INTO cost_source_streams (id, team_id, source_kind, role, provider, scope_type, usage_account, vantage, metric, "
        f"grouping_version, config_sha256) VALUES ('{sid}', '{team}', '{kind}', '{role}', 'aws', '{scope}', '{account}', '{vantage}', "
        f"'aws:UnblendedCost', '{version}', sha256('{version}'));"
    )


def _record(
    rid,
    team,
    stream,
    line_kind="aws:Usage",
    cls="usage",
    svc="Amazon EC2",
    amount="100",
    key="",
    kind="provider",
    currency="USD",
):
    usd = amount if currency == "USD" else "NULL"
    return (
        "INSERT INTO cost_source_records (id, team_id, stream_id, source_kind, usage_date, dim_1, line_kind, line_key, currency, "
        f"canonical_service, charge_class, amount, amount_usd, cost_bucket, last_generation) VALUES ('{rid}', '{team}', '{stream}', "
        f"'{kind}', '2026-10-20', '{svc}', '{line_kind}', '{key}', '{currency}', '{svc}', '{cls}', {amount}, {usd}, 'ec2', 1);"
    )


def _fact(team, record, svc="Amazon EC2", cls="usage", currency="USD", registered="shadow", billable="false"):
    return (
        "INSERT INTO billing_canonical_facts (team_id, provider, billing_account, usage_account, usage_date, canonical_service, "
        f"charge_class, currency, first_record_id, registered_in, first_billable) VALUES ('{team}', 'aws', '', 'aws:acct:111122223333', "
        f"'2026-10-20', '{svc}', '{cls}', '{currency}', '{record}', '{registered}', {billable});"
    )


SEED = f"""
INSERT INTO teams (id, name) VALUES ('{T1}', 'Acme Robotics'), ('{T2}', 'Birch Labs');
INSERT INTO users (id, email, hashed_password) VALUES ('{ALICE}', 'alice@acme.test', 'x'), ('{BOB}', 'bob@acme.test', 'x');
INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted) VALUES
  ('{C1}', '{T1}', 'aws', 'Acme payer', 'x'), ('{C2}', '{T1}', 'aws', 'Acme member', 'x'), ('{C3}', '{T2}', 'aws', 'Birch', 'x');
INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T1}', 'shadow');
{_stream(PAYER, T1, "aws:caller:999900000001")}
{_stream(MEMBER, T1, "aws:caller:111122223333")}
{_stream(PAYER_V2, T1, "aws:caller:999900000001", version="aws.v2.service+record_type+usage_type")}
{_stream(TAGS, T1, "aws:caller:999900000001", version="aws.v1.service+tag:Team", role="attribution")}
{_stream(BIRCH, T2, "aws:caller:111122223333")}
INSERT INTO cost_source_streams (id, team_id, source_kind, role, provider, scope_type, usage_account, vantage, metric, grouping_version,
  config_sha256) VALUES ('{MANUAL}', '{T1}', 'manual', 'cost', 'aws', 'manual', 'manual:api', 'manual:api', 'manual:amount', 'manual.v1', sha256('m'));
INSERT INTO cost_source_stream_bindings (team_id, stream_id, connection_id) VALUES ('{T1}', '{PAYER}', '{C1}'), ('{T1}', '{MEMBER}', '{C2}');
{_record("e1000000-0000-0000-0000-000000000001", T1, PAYER)}
{_record("e2000000-0000-0000-0000-000000000002", T1, MEMBER)}
{_record("e3000000-0000-0000-0000-000000000003", T2, BIRCH)}
{_fact(T1, "e1000000-0000-0000-0000-000000000001")}
INSERT INTO cost_source_observations (id, team_id, record_id, actor_user_id, generation, change_kind, observed_amount, observed_currency,
  is_estimated, payload_sha256) VALUES (gen_random_uuid(), '{T1}', 'e1000000-0000-0000-0000-000000000001', '{ALICE}', 1, 'inserted', 100,
  'USD', false, sha256('o'));
INSERT INTO cost_source_authority_history (id, team_id, provider, billing_account, usage_account, to_stream_id, changed_by, reason)
VALUES (gen_random_uuid(), '{T1}', 'aws', '', 'aws:acct:111122223333', '{PAYER}', '{ALICE}', 'initial');
INSERT INTO cost_snapshots (id, team_id, date, provider, gpu_type, cost_usd) VALUES
  ('e9000000-0000-0000-0000-000000000009', '{T1}', '2026-10-01', 'aws', 'ec2', 250.00);
"""


@pytest.fixture(scope="module")
def engine():
    with scratch_database("heliox_ledger_constraints") as url:
        alembic(url, "upgrade", "head")
        eng = create_engine(url)
        with eng.begin() as conn:
            conn.exec_driver_sql(SEED)
        yield eng
        eng.dispose()


@contextmanager
def rolled_back(engine, role: str | None = None):
    """A connection whose work is always rolled back; optionally acting as a role."""
    conn = engine.connect()
    tx = conn.begin()
    try:
        if role:
            conn.exec_driver_sql(f"SET LOCAL ROLE {role}")
        yield conn
    finally:
        tx.rollback()
        conn.close()


def expect_failure(engine, statement: str, sqlstate: str, match: str, role: str | None = None) -> None:
    """The statement must fail with this SQLSTATE and the named constraint (or a message containing `match`)."""
    with rolled_back(engine, role) as conn:
        with pytest.raises(DBAPIError) as caught:
            conn.exec_driver_sql(statement.replace("%", "%%"))
            conn.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")
    orig = caught.value.orig
    assert orig.pgcode == sqlstate, f"{orig.pgcode}: {orig}"
    assert orig.diag.constraint_name == match or match in str(orig), str(orig)


def succeeds(engine, statement: str, role: str | None = None) -> None:
    with rolled_back(engine, role) as conn:
        conn.exec_driver_sql(statement.replace("%", "%%"))
        conn.exec_driver_sql("SET CONSTRAINTS ALL IMMEDIATE")


# ── Live mode is impossible ───────────────────────────────────────────────────────

LIVE_ATTEMPTS = {
    "activate live for a new team": (
        f"INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T2}', 'live')",
        "ck_ledger_settings_gate_no_live",
    ),
    "move a shadow team to live": (
        f"UPDATE team_cost_ledger_settings SET ledger_mode = 'live' WHERE team_id = '{T1}'",
        "ck_ledger_settings_gate_no_live",
    ),
    "move an off team straight to live": (
        f"INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T2}', 'off'); "
        f"UPDATE team_cost_ledger_settings SET ledger_mode = 'live' WHERE team_id = '{T2}'",
        "ck_ledger_settings_gate_no_live",
    ),
    "switch billing to the ledger pathway": (
        f"UPDATE team_cost_ledger_settings SET billing_pathway = 'ledger' WHERE team_id = '{T1}'",
        "ck_ledger_settings_gate_legacy_billing",
    ),
    "switch billing to first-ingested": (
        f"UPDATE team_cost_ledger_settings SET billing_basis = 'first_ingested' WHERE team_id = '{T1}'",
        "ck_ledger_settings_gate_legacy_billing",
    ),
    "create a ledger-derived total": (
        f"INSERT INTO cost_snapshots (id, team_id, date, provider, gpu_type, cost_usd, source_mode, completeness, ledger_updated_at) "
        f"VALUES (gen_random_uuid(), '{T1}', '2026-10-20', 'aws', 'ec2', 90, 'ledger', 'complete', now())",
        "ck_cost_snapshots_gate_legacy_only",
    ),
    "convert a legacy total to ledger": (
        "UPDATE cost_snapshots SET source_mode = 'ledger', completeness = 'complete', ledger_updated_at = now()",
        "ck_cost_snapshots_gate_legacy_only",
    ),
    "register a billable fact": (
        _fact(T1, "e2000000-0000-0000-0000-000000000002", svc="Amazon S3", registered="live", billable="true"),
        "ck_facts_gate_not_billable",
    ),
    "record non-shadow billable usage": (
        f"INSERT INTO billing_usage_ledger (id, team_id, event_type, idempotency_key, basis, quantity, shadow, accrual_date) "
        f"VALUES (gen_random_uuid(), '{T1}', 'ingestion', 'k1', 'first_ingested', 3, false, current_date)",
        "ck_usage_ledger_gate_shadow_only",
    ),
    "apply a reconciliation": (
        f"INSERT INTO cost_reconciliation_batches (id, team_id, date_from, date_to, scope, expected_inventory, status, proposed_by, "
        f"approved_by, approved_at, approval_reason, batch_fingerprint, expires_at, applied_at) VALUES (gen_random_uuid(), '{T1}', "
        f"'2026-10-01', '2026-10-01', '{{}}', '[]', 'applied', '{ALICE}', '{BOB}', now(), 'ok', sha256('b'), now(), now())",
        "ck_batches_gate_no_apply",
    ),
}


@pytest.mark.parametrize("statement,constraint", LIVE_ATTEMPTS.values(), ids=LIVE_ATTEMPTS.keys())
def test_live_mode_is_impossible(engine, statement, constraint):
    expect_failure(engine, statement, "23514", constraint)


def test_shadow_and_off_remain_possible(engine):
    succeeds(engine, f"INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES ('{T2}', 'shadow')")
    succeeds(engine, f"UPDATE team_cost_ledger_settings SET ledger_mode = 'off' WHERE team_id = '{T1}'")


def test_no_application_code_uses_the_ledger_yet():
    """Scheduler, API routes, Stripe exporter and tasks reference none of the new tables or models."""
    names = re.compile(
        r"cost_source_|cost_sync_|cost_reconciliation|billing_canonical_facts|billing_usage_ledger|manual_cost_requests|"
        r"team_cost_ledger_settings|cost_ledger|CostSource|CostSync|CostReconciliation|BillingCanonicalFact|BillingUsageLedger|"
        r"TeamCostLedgerSettings|ManualCostRequest|\bsource_mode\b|\bledger_mode\b|pipeline\s*=\s*['\"]ledger"
    )
    allowed = {
        APP_DIR / "models" / "cost_ledger.py",
        APP_DIR / "models" / "cost_ledger_ddl.py",
        APP_DIR / "models" / "__init__.py",
        APP_DIR / "models" / "cost.py",
        APP_DIR / "integrations" / "models.py",
        # Step 6E shadow-only service; `cost_ledger` above still catches anything that imports it
        APP_DIR / "services" / "cost_ledger.py",
        # Step 6F shadow-only orchestration, adapters and its disabled-by-default task module
        *(APP_DIR / "services" / "ledger_shadow").glob("*.py"),
        *(APP_DIR / "integrations" / "ledger").glob("*.py"),
        APP_DIR / "tasks" / "ledger_shadow_tasks.py",
    }
    users = [
        str(p.relative_to(APP_DIR)) for p in APP_DIR.rglob("*.py") if p not in allowed and names.search(p.read_text())
    ]
    assert users == []
    # The worker path is reached only by the conditional import below; nothing schedules or calls it
    shadow = re.compile(r"ledger_shadow|integrations\.ledger|ledger\.shadow_sync|ledger\.reap_abandoned_runs")
    reached_from = {
        str(p.relative_to(APP_DIR)) for p in APP_DIR.rglob("*.py") if p not in allowed and shadow.search(p.read_text())
    }
    assert reached_from == {"celery_app.py"}
    celery_source = (APP_DIR / "celery_app.py").read_text()
    assert "if settings.LEDGER_SHADOW_WORKER_ENABLED:\n    import app.tasks.ledger_shadow_tasks" in celery_source
    assert "ledger." not in celery_source.split("beat_schedule = {")[1].split("\n}\n")[0]


# ── Financial identity ────────────────────────────────────────────────────────────


def test_same_bill_observed_through_two_connections_is_one_billing_fact(engine):
    # The member view (connection C2) of the payer's expense maps to the same canonical fact
    expect_failure(engine, _fact(T1, "e2000000-0000-0000-0000-000000000002"), "23505", "billing_canonical_facts_pkey")


def test_distinct_charges_classes_and_currencies_stay_distinct(engine):
    rid = "e4000000-0000-0000-0000-000000000004"
    succeeds(
        engine,
        _record(rid, T1, PAYER, line_kind="aws:Credit", cls="credit", amount="-10")
        + _fact(T1, rid, cls="credit")
        + _fact(T1, rid, svc="Amazon SageMaker")
        + _fact(T1, rid, currency="EUR"),
    )


def test_multiple_credits_in_one_service_and_day_are_separate_records_but_one_fact(engine):
    sud, promo = "e5000000-0000-0000-0000-000000000005", "e6000000-0000-0000-0000-000000000006"
    two_credits = _record(
        sud, T1, PAYER, line_kind="gcp:credit:SUSTAINED_USAGE_DISCOUNT", cls="discount", amount="-6"
    ) + _record(promo, T1, PAYER, line_kind="gcp:credit:COMMITTED_USAGE_DISCOUNT", cls="discount", amount="-4")
    succeeds(engine, two_credits + _fact(T1, sud, cls="discount"))
    expect_failure(
        engine,
        two_credits + _fact(T1, sud, cls="discount") + _fact(T1, promo, cls="discount"),
        "23505",
        "billing_canonical_facts_pkey",
    )


def test_a_new_grouping_layout_is_a_new_stream_but_not_a_new_fact(engine):
    rid = "e7000000-0000-0000-0000-000000000007"
    succeeds(engine, _record(rid, T1, PAYER_V2))
    expect_failure(engine, _record(rid, T1, PAYER_V2) + _fact(T1, rid), "23505", "billing_canonical_facts_pkey")


def test_canonical_service_rename_is_a_new_fact_documented_limitation(engine):
    """A provider renaming a service yields a different canonical_service and therefore a new fact."""
    rid = "e8000000-0000-0000-0000-000000000008"
    succeeds(
        engine,
        _record(rid, T1, PAYER_V2, svc="Amazon Elastic Compute Cloud - Compute")
        + _fact(T1, rid, svc="Amazon Elastic Compute Cloud - Compute"),
    )


def test_duplicate_manual_entry_identity_is_rejected(engine):
    manual = _record(
        "ea000000-0000-0000-0000-00000000000a", T1, MANUAL, line_kind="manual:charge", key="default", kind="manual"
    )
    succeeds(engine, manual)
    duplicate = _record(
        "eb000000-0000-0000-0000-00000000000b", T1, MANUAL, line_kind="manual:charge", key="default", kind="manual"
    )
    expect_failure(engine, manual + duplicate, "23505", "uq_cost_source_records_identity")
    expect_failure(
        engine,
        _record("ec000000-0000-0000-0000-00000000000c", T1, MANUAL, line_kind="manual:charge", key="", kind="manual"),
        "23514",
        "ck_records_manual_entry_key",
    )


def test_records_without_a_billable_charge_dimension_cannot_become_facts(engine):
    # Attribution views and layouts without a charge dimension use charge_class 'other': never billable
    rid = "ed000000-0000-0000-0000-00000000000d"
    expect_failure(
        engine,
        _record(rid, T1, TAGS, line_kind="aws:tag", cls="other") + _fact(T1, rid, cls="other"),
        "23514",
        "ck_facts_charge_class",
    )
    expect_failure(engine, _record(rid, T1, PAYER, svc=""), "23514", "ck_records_canonical_service")


def test_cross_tenant_references_are_rejected(engine):
    expect_failure(engine, _record("ee000000-0000-0000-0000-00000000000e", T2, PAYER), "23503", "fk_records_stream")
    expect_failure(
        engine, _fact(T1, "e3000000-0000-0000-0000-000000000003", svc="Amazon S3"), "23503", "fk_facts_first_record"
    )
    expect_failure(
        engine,
        f"INSERT INTO cost_source_stream_bindings (team_id, stream_id, connection_id) VALUES ('{T1}', '{PAYER}', '{C3}')",
        "23503",
        "fk_bindings_connection",
    )
    # The same account observed by another tenant is that tenant's own fact
    succeeds(engine, _fact(T2, "e3000000-0000-0000-0000-000000000003"))


def test_authority_switching(engine):
    authority = (
        "INSERT INTO cost_source_authority (team_id, provider, billing_account, usage_account, stream_id, set_by, reason) "
        f"VALUES ('{T1}', 'aws', '', 'aws:acct:111122223333', '{{stream}}', '{ALICE}', 'r')"
    )
    succeeds(engine, authority.format(stream=PAYER) + f"; UPDATE cost_source_authority SET stream_id = '{MEMBER}'")
    expect_failure(engine, authority.format(stream=TAGS), "23503", "fk_authority_stream")
    expect_failure(
        engine, "UPDATE cost_source_authority_history SET reason = 'rewritten'", "42501", "heliox_audit_immutable"
    )


def test_source_stream_identity_is_unique(engine):
    expect_failure(
        engine, _stream(str(uuid.uuid4()), T1, "aws:caller:999900000001"), "23505", "uq_cost_source_streams_identity"
    )
    expect_failure(
        engine,
        _stream(str(uuid.uuid4()), T1, "manual:x", role="attribution", kind="manual", account="manual:x"),
        "23514",
        "ck_streams_role",
    )


def test_shadow_history_can_never_become_billable(engine):
    expect_failure(
        engine,
        "UPDATE billing_canonical_facts SET first_billable = true, registered_in = 'live'",
        "42501",
        "heliox_audit_immutable",
    )
    expect_failure(engine, "DELETE FROM billing_canonical_facts", "42501", "heliox_audit_immutable")


# ── Privileges (disposable roles) ─────────────────────────────────────────────────

APPEND_ONLY = "cost_source_observations, billing_canonical_facts, billing_usage_ledger, cost_reconciliation_attempts, cost_source_authority_history"


@pytest.fixture(scope="module")
def app_role(engine):
    """A restricted application role, as the separately approved privileges script would grant it."""
    role = f"heliox_test_app_{uuid.uuid4().hex[:10]}"
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
        conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}")
        conn.exec_driver_sql(f"REVOKE UPDATE, DELETE ON {APPEND_ONLY} FROM {role}")
        conn.exec_driver_sql(f"REVOKE DELETE ON cost_source_records FROM {role}")
    yield role
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DROP OWNED BY {role}")
        conn.exec_driver_sql(f"DROP ROLE {role}")


def test_app_role_can_append_audit_rows(engine, app_role):
    succeeds(
        engine,
        "INSERT INTO cost_source_observations (id, team_id, record_id, actor_user_id, generation, change_kind, observed_amount, "
        f"observed_currency, is_estimated, payload_sha256) VALUES (gen_random_uuid(), '{T1}', 'e1000000-0000-0000-0000-000000000001', "
        f"'{ALICE}', 2, 'unchanged', 100, 'USD', false, sha256('a'))",
        role=app_role,
    )


APP_ROLE_DENIED = {
    "update an observation": (
        "UPDATE cost_source_observations SET observed_amount = 0",
        "permission denied for table cost_source_observations",
    ),
    "delete an observation": (
        "DELETE FROM cost_source_observations",
        "permission denied for table cost_source_observations",
    ),
    "delete a record": ("DELETE FROM cost_source_records", "permission denied for table cost_source_records"),
    "rewrite a billing fact": (
        "UPDATE billing_canonical_facts SET first_billable = true",
        "permission denied for table billing_canonical_facts",
    ),
    "truncate observations": (
        "TRUNCATE cost_source_observations",
        "permission denied for table cost_source_observations",
    ),
    "disable the audit trigger": (
        "ALTER TABLE cost_source_observations DISABLE TRIGGER trg_cost_source_observations_guard",
        "must be owner of table",
    ),
    "drop the audit trigger": (
        "DROP TRIGGER trg_cost_source_observations_guard ON cost_source_observations",
        "must be owner of relation",
    ),
    "skip triggers": ("SET session_replication_role = replica", "permission denied to set parameter"),
    "replace the guard function": (
        "CREATE OR REPLACE FUNCTION cost_audit_guard() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN OLD; END'",
        "permission denied for schema public",
    ),
    "drop a gate constraint": (
        "ALTER TABLE team_cost_ledger_settings DROP CONSTRAINT ck_ledger_settings_gate_no_live",
        "must be owner of table",
    ),
    "create a table": ("CREATE TABLE sneaky (x int)", "permission denied for schema public"),
}


@pytest.mark.parametrize("statement,message", APP_ROLE_DENIED.values(), ids=APP_ROLE_DENIED.keys())
def test_app_role_cannot_change_audit_or_schema(engine, app_role, statement, message):
    expect_failure(engine, statement, "42501", message, role=app_role)


def test_guard_holds_even_if_update_is_granted(engine):
    """Defence in depth: a non-owner role WITH UPDATE/DELETE privilege is still stopped by the trigger."""
    role = f"heliox_test_writer_{uuid.uuid4().hex[:10]}"
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE ROLE {role} NOLOGIN")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {role}")
        conn.exec_driver_sql(f"GRANT SELECT, UPDATE, DELETE ON cost_source_observations, teams TO {role}")
    try:
        expect_failure(
            engine,
            "UPDATE cost_source_observations SET observed_amount = 0",
            "42501",
            "heliox_audit_immutable",
            role=role,
        )
        expect_failure(engine, "DELETE FROM cost_source_observations", "42501", "heliox_audit_immutable", role=role)
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"DROP OWNED BY {role}")
            conn.exec_driver_sql(f"DROP ROLE {role}")


def test_documented_limitation_owner_and_superuser_can_bypass_the_guard(engine):
    """Not a guarantee: the table owner can disable the trigger and a superuser can skip triggers (both rolled back)."""
    succeeds(
        engine,
        "ALTER TABLE cost_source_observations DISABLE TRIGGER trg_cost_source_observations_guard; "
        "UPDATE cost_source_observations SET observed_amount = 0",
    )
    succeeds(engine, "SET LOCAL session_replication_role = replica; DELETE FROM cost_source_observations")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM cost_source_observations")).scalar() == 1
        assert (
            conn.execute(
                text("SELECT tgenabled FROM pg_trigger WHERE tgname = 'trg_cost_source_observations_guard'")
            ).scalar()
            == "O"
        )
