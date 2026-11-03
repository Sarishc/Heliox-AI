"""
Shadow-only cost ledger service (app.services.cost_ledger) on real PostgreSQL at migration 038.

Every scenario checks the resulting database state. Each sync runs as a caller would: one
transaction to start the run and take the lease, one to publish. Concurrency tests use separate
sessions in separate threads. Nothing here may create billable usage or change legacy totals.
"""

import threading
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from postgres_scratch import alembic, needs_postgres, scratch_database
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.cost_ledger import (
    CostLedgerService,
    InvalidCostLine,
    LedgerDisabled,
    Publication,
    StreamIdentity,
    TenantMismatch,
    normalize_line,
)

pytestmark = needs_postgres

A, B, D = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ALICE = uuid.uuid4()
CONN = {name: uuid.uuid4() for name in ("payer", "member", "birch", "gcp", "gcp_copy", "az_sub", "az_ba", "dormant")}
DAY = date(2026, 10, 20)
LEGACY_ID = uuid.uuid4()


@pytest.fixture(scope="module")
def engine():
    with scratch_database("heliox_ledger_service") as url:
        alembic(url, "upgrade", "head")
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(
                text("INSERT INTO teams (id, name) VALUES (:a, 'Acme Robotics'), (:b, 'Birch Labs'), (:d, 'Dormant')"),
                {"a": A, "b": B, "d": D},
            )
            c.execute(
                text("INSERT INTO users (id, email, hashed_password) VALUES (:u, 'alice@acme.test', 'x')"), {"u": ALICE}
            )
            owners = {"birch": B, "dormant": D}
            for name, cid in CONN.items():
                c.execute(
                    text(
                        "INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted) "
                        "VALUES (:id, :t, 'aws', :n, 'x')"
                    ),
                    {"id": cid, "t": owners.get(name, A), "n": name},
                )
            c.execute(
                text(
                    "INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:a, 'shadow'), (:b, 'shadow')"
                ),
                {"a": A, "b": B},
            )
            c.execute(
                text(
                    "INSERT INTO cost_snapshots (id, team_id, date, provider, gpu_type, cost_usd) "
                    "VALUES (:id, :a, '2026-10-01', 'aws', 'ec2', 250.00)"
                ),
                {"id": LEGACY_ID, "a": A},
            )
        yield eng
        eng.dispose()


def stream(
    engine,
    connections,
    *,
    team=A,
    provider="aws",
    account=None,
    vantage="aws:caller:999900000001",
    version="aws.v1.service+record_type",
    role="cost",
    ba="",
    scope="aws:linked_account",
):
    identity = StreamIdentity(
        team_id=team,
        provider=provider,
        scope_type=scope,
        billing_account=ba,
        usage_account=account or f"{provider}:acct:{uuid.uuid4().hex[:12]}",
        vantage=vantage,
        metric="UnblendedCost",
        grouping_version=version,
        config={"v": version},
        role=role,
    )
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        sid = svc.register_stream(identity)
        for c in connections:
            svc.bind_connection(sid, CONN[c])
    return sid, identity


def line(
    amount,
    *,
    day=DAY,
    svc="Amazon EC2",
    cls="usage",
    kind="aws:Usage",
    bucket="ec2",
    cur="USD",
    usd=None,
    fx=None,
    d2="",
    key="",
    est=False,
):
    return normalize_line(
        usage_date=day,
        line_kind=kind,
        canonical_service=svc,
        charge_class=cls,
        cost_bucket=bucket,
        currency=cur,
        amount=Decimal(str(amount)),
        amount_usd=usd,
        fx_rate=fx,
        fx_source="provider" if fx else None,
        dim_1=svc,
        dim_2=d2,
        line_key=key,
        is_estimated=est,
    )


def sync(engine, conn, sid, lines, *, start=DAY, days=1, complete=True, exempt=False, hold=None):
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        run = svc.start_run(CONN[conn], billing_exempt=exempt)
        token = svc.acquire_lease(run)
    try:
        with Session(engine) as s, s.begin():
            svc = CostLedgerService(s)
            out = svc.publish(Publication(run, 1, token, sid, start, start + timedelta(days=days), lines, complete))
            if hold:
                s.execute(text("SELECT pg_sleep(:t)"), {"t": hold})
            svc.finish_run(run)
    except Exception:
        # As a worker would: the publish rolled back; record the failed run and release its lease
        with Session(engine) as s, s.begin():
            CostLedgerService(s).finish_run(run, status="failed")
        raise
    return out


def total(engine, team, day=DAY, provider="aws", bucket="ec2"):
    with Session(engine) as s:
        found = [
            t
            for t in CostLedgerService(s).shadow_totals(team, [day])
            if (t.provider, t.cost_bucket) == (provider, bucket)
        ]
    return found[0] if found else None


def q(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def money(t):
    return (t.amount_usd, t.completeness)


# 1-6: idempotency, corrections, negatives


def test_01_first_ingestion_of_100(engine):
    sid, _ = stream(engine, ["payer"])
    out = sync(engine, "payer", sid, [line(100)])
    assert (out.inserted, out.corrected) == (1, 0)
    assert q(engine, "SELECT amount FROM cost_source_records WHERE stream_id = :s", s=sid) == Decimal("100")
    assert (
        q(
            engine,
            "SELECT count(*) FROM cost_source_observations o JOIN cost_source_records r ON r.id = o.record_id "
            "WHERE r.stream_id = :s AND o.change_kind = 'inserted'",
            s=sid,
        )
        == 1
    )


def test_02_identical_second_ingestion_changes_nothing(engine):
    day = DAY + timedelta(1)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day)], start=day)
    out = sync(engine, "payer", sid, [line(100, day=day)], start=day)
    assert (out.inserted, out.corrected, out.unchanged) == (0, 0, 1)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")


def test_03_ten_repeats_stay_100(engine):
    day = DAY + timedelta(2)
    sid, _ = stream(engine, ["payer"])
    for _ in range(10):
        sync(engine, "payer", sid, [line(100, day=day)], start=day)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT count(*) FROM cost_source_records WHERE stream_id = :s", s=sid) == 1
    assert (
        q(
            engine,
            "SELECT count(*) FROM billing_canonical_facts WHERE first_record_id IN "
            "(SELECT id FROM cost_source_records WHERE stream_id = :s)",
            s=sid,
        )
        == 1
    )


def test_04_correction_100_to_80(engine):
    day = DAY + timedelta(3)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day)], start=day)
    out = sync(engine, "payer", sid, [line(80, day=day)], start=day)
    assert out.corrected == 1
    assert money(total(engine, A, day)) == (Decimal("80.00"), "complete")
    assert q(
        engine,
        "SELECT previous_amount FROM cost_source_observations o JOIN cost_source_records r "
        "ON r.id = o.record_id WHERE r.stream_id = :s AND change_kind = 'corrected'",
        s=sid,
    ) == Decimal("100")


def test_05_correction_100_to_zero(engine):
    day = DAY + timedelta(4)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day)], start=day)
    sync(engine, "payer", sid, [line(0, day=day)], start=day)
    assert money(total(engine, A, day)) == (Decimal("0.00"), "complete")


def test_06_refund_of_15_is_netted(engine):
    day = DAY + timedelta(5)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day), line(-15, day=day, cls="refund", kind="aws:Refund")], start=day)
    assert money(total(engine, A, day)) == (Decimal("85.00"), "complete")


# 7-11: distinct sources and overlapping observers


def test_07_distinct_accounts_add_up(engine):
    day = DAY + timedelta(6)
    for amount in (60, 40, 25):
        sid, _ = stream(engine, ["payer"])
        sync(engine, "payer", sid, [line(amount, day=day)], start=day)
    assert money(total(engine, A, day)) == (Decimal("125.00"), "complete")


def test_08_two_connections_observing_one_aws_bill(engine):
    day = DAY + timedelta(7)
    account = f"aws:acct:{uuid.uuid4().hex[:12]}"
    payer, _ = stream(engine, ["payer"], account=account)
    member, _ = stream(engine, ["member"], account=account, vantage="aws:caller:member")
    sync(engine, "payer", payer, [line(100, day=day)], start=day)
    out = sync(engine, "member", member, [line(100, day=day)], start=day)
    assert (out.quarantined, out.new_shadow_facts) == (0, 0)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")


def test_09_separate_accounts_within_one_connection(engine):
    day = DAY + timedelta(8)
    s1, _ = stream(engine, ["payer"])
    s2, _ = stream(engine, ["payer"])
    sync(engine, "payer", s1, [line(70, day=day)], start=day)
    sync(engine, "payer", s2, [line(30, day=day)], start=day)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")


def test_10_overlapping_gcp_export_views(engine):
    day = DAY + timedelta(9)
    kw = dict(
        provider="gcp",
        account="gcp:project:ml-prod-x",
        ba="gcp:ba:0A1B2C",
        scope="gcp:billing_export",
        version="gcp.v1",
    )
    main, _ = stream(engine, ["gcp"], vantage="gcp:table:billing.export", **kw)
    copy, _ = stream(engine, ["gcp_copy"], vantage="gcp:table:analytics.copy", **kw)
    lines = [
        line(100, day=day, svc="6F81", kind="gcp:cost:regular", bucket="compute-engine", key="202610"),
        line(
            -10,
            day=day,
            svc="6F81",
            cls="discount",
            kind="gcp:credit:SUSTAINED_USAGE_DISCOUNT",
            bucket="compute-engine",
            key="202610",
        ),
    ]
    sync(engine, "gcp", main, lines, start=day)
    sync(engine, "gcp_copy", copy, lines, start=day)
    assert money(total(engine, A, day, "gcp", "compute-engine")) == (Decimal("90.00"), "complete")


def test_11_overlapping_azure_billing_scopes(engine):
    day = DAY + timedelta(10)
    kw = dict(provider="azure", account="azure:sub:00000000-0000-0000-0000-0000000000aa")
    sub, _ = stream(engine, ["az_sub"], vantage="azure:scope:sub", scope="azure:subscription", version="az.sub", **kw)
    ba, _ = stream(engine, ["az_ba"], vantage="azure:scope:ba", scope="azure:billing_account", version="az.ba", **kw)
    vm = dict(day=day, svc="Virtual Machines", kind="azure:Cost", bucket="azure_vm")
    sync(engine, "az_sub", sub, [line(54, **vm)], start=day)
    sync(engine, "az_ba", ba, [line(54, d2="00000000-0000-0000-0000-0000000000aa", **vm)], start=day)
    assert money(total(engine, A, day, "azure", "azure_vm")) == (Decimal("54.00"), "complete")


# 12-15: tenancy, concurrency, rollback


def test_12_metadata_cannot_redirect_cost_to_another_tenant(engine):
    day = DAY + timedelta(11)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day, d2="Team$Birch Labs")], start=day)
    assert q(engine, "SELECT team_id FROM cost_source_records WHERE stream_id = :s", s=sid) == A
    assert total(engine, B, day) is None
    birch, _ = stream(engine, ["birch"], team=B)
    observations = q(engine, "SELECT count(*) FROM cost_source_observations")
    with pytest.raises(TenantMismatch):
        sync(engine, "payer", birch, [line(5, day=day)], start=day)
    # The refused publish left nothing: the service checks tenancy before its first write
    for table in ("cost_source_records", "cost_sync_run_streams", "cost_source_stream_days"):
        assert q(engine, f"SELECT count(*) FROM {table} WHERE stream_id = :s", s=birch) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_coverage WHERE team_id = :b", b=B) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_observations") == observations
    # Test-owned cleanup (a worker's job in production) failed the run and released the lease
    assert q(engine, "SELECT holder_run_id FROM cost_sync_leases WHERE connection_id = :c", c=CONN["payer"]) is None
    assert (
        q(
            engine,
            "SELECT count(*) FROM integration_sync_runs WHERE connection_id = :c AND phase IN "
            "('queued','leased','fetching','publishing')",
            c=CONN["payer"],
        )
        == 0
    )


def test_13_simultaneous_inserts_with_the_same_identity(engine):
    identity = StreamIdentity(
        team_id=A,
        provider="aws",
        scope_type="aws:linked_account",
        usage_account="aws:acct:race0000",
        vantage="v",
        metric="m",
        grouping_version="g",
        config={},
    )
    ids = []

    def first():
        with Session(engine) as s, s.begin():
            ids.append(CostLedgerService(s).register_stream(identity))
            s.execute(text("SELECT pg_sleep(1.5)"))

    t = threading.Thread(target=first)
    t.start()
    time.sleep(0.5)
    started = time.monotonic()
    with Session(engine) as s, s.begin():
        ids.append(CostLedgerService(s).register_stream(identity))
    waited = time.monotonic() - started
    t.join()
    assert ids[0] == ids[1] and waited >= 0.8
    assert q(engine, "SELECT count(*) FROM cost_source_streams WHERE usage_account = 'aws:acct:race0000'") == 1


def test_14_concurrent_publications_are_serialized_and_both_count(engine):
    day = DAY + timedelta(12)
    s1, _ = stream(engine, ["payer"])
    s2, _ = stream(engine, ["member"])
    t = threading.Thread(target=lambda: sync(engine, "payer", s1, [line(60, day=day)], start=day, hold=2))
    t.start()
    time.sleep(0.7)
    started = time.monotonic()
    sync(engine, "member", s2, [line(25, day=day)], start=day)
    waited = time.monotonic() - started
    t.join()
    assert waited >= 1.0
    assert money(total(engine, A, day)) == (Decimal("85.00"), "complete")


def test_15_injected_failure_rolls_back_everything(engine):
    day = DAY + timedelta(13)
    sid, _ = stream(engine, ["payer"])
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        run = svc.start_run(CONN["payer"])
        token = svc.acquire_lease(run)
    with pytest.raises(RuntimeError, match="injected"):
        with Session(engine) as s, s.begin():
            CostLedgerService(s).publish(
                Publication(run, 1, token, sid, day, day + timedelta(1), [line(100, day=day)], True)
            )
            raise RuntimeError("injected")
    for table in ("cost_source_records", "cost_sync_run_streams", "cost_source_stream_days"):
        assert q(engine, f"SELECT count(*) FROM {table} WHERE stream_id = :s", s=sid) == 0
    with Session(engine) as s, s.begin():
        CostLedgerService(s).finish_run(run)


# 16-21: coverage, staleness, estimates, currency


def test_16_incomplete_fetch_writes_nothing(engine):
    day = DAY + timedelta(14)
    sid, _ = stream(engine, ["payer"])
    out = sync(engine, "payer", sid, [line(100, day=day)], start=day, complete=False)
    assert out.incomplete and out.inserted == 0
    assert q(engine, "SELECT count(*) FROM cost_source_records WHERE stream_id = :s", s=sid) == 0
    assert q(engine, "SELECT count(*) FROM cost_source_coverage WHERE authoritative_stream_id = :s", s=sid) == 0


def test_17_missing_rows_under_incomplete_coverage_are_not_retired(engine):
    day = DAY + timedelta(15)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day), line(40, day=day, svc="Amazon S3")], start=day)
    out = sync(engine, "payer", sid, [line(100, day=day)], start=day, complete=False)
    assert out.retired == 0
    assert money(total(engine, A, day)) == (Decimal("140.00"), "complete")
    out = sync(engine, "payer", sid, [line(100, day=day)], start=day)
    assert out.retired == 1
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")


def test_18_suspicious_empty_day_is_held(engine):
    day = DAY + timedelta(16)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day)], start=day)
    out = sync(engine, "payer", sid, [], start=day)
    assert (out.held, out.retired) == (1, 0)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "incomplete")


def test_19_stale_result_cannot_overwrite_a_newer_one(engine):
    day = DAY + timedelta(17)
    sid, _ = stream(engine, ["payer"])
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        old_run = svc.start_run(CONN["payer"])
        svc.acquire_lease(old_run)
        s.execute(
            text(
                "UPDATE integration_sync_runs SET fetch_started_at = now() - interval '1 hour', phase = 'failed' "
                "WHERE id = :r"
            ),
            {"r": old_run},
        )
        s.execute(
            text(
                "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
                "WHERE holder_run_id = :r"
            ),
            {"r": old_run},
        )
    sync(engine, "payer", sid, [line(80, day=day)], start=day)
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        s.execute(text("UPDATE integration_sync_runs SET phase = 'leased' WHERE id = :r"), {"r": old_run})
        token = svc.acquire_lease(old_run)
        s.execute(
            text("UPDATE integration_sync_runs SET fetch_started_at = now() - interval '1 hour' WHERE id = :r"),
            {"r": old_run},
        )
        out = svc.publish(Publication(old_run, 1, token, sid, day, day + timedelta(1), [line(100, day=day)], True))
        svc.finish_run(old_run)
    assert (out.stale, out.corrected, out.inserted) == (1, 0, 0)
    assert money(total(engine, A, day)) == (Decimal("80.00"), "complete")


def test_20_estimated_is_never_presented_as_final(engine):
    day = DAY + timedelta(18)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(90, day=day, est=True)], start=day)
    assert money(total(engine, A, day)) == (Decimal("90.00"), "estimated")
    sync(engine, "payer", sid, [line(95, day=day)], start=day)
    assert money(total(engine, A, day)) == (Decimal("95.00"), "complete")


def test_21_unconverted_currency_is_incomplete_not_zero(engine):
    day = DAY + timedelta(19)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(50, day=day, cur="EUR")], start=day)
    t = total(engine, A, day)
    assert (t.amount_usd, t.completeness, t.unconverted) == (None, "incomplete", 1)
    with pytest.raises(InvalidCostLine):
        normalize_line(
            usage_date=day,
            line_kind="x",
            canonical_service="s",
            charge_class="usage",
            cost_bucket="b",
            currency="EUR",
            amount=50.0,
        )
    sync(engine, "payer", sid, [line(50, day=day, cur="EUR", usd=Decimal("54"), fx=Decimal("1.08"))], start=day)
    assert money(total(engine, A, day)) == (Decimal("54.00"), "complete")
    assert (
        q(engine, "SELECT currency || amount::text FROM cost_source_records WHERE stream_id = :s", s=sid)
        == "EUR50.0000000000"
    )


# 22-25: credits, layouts, conflicts, authority


def test_22_multiple_gcp_credits_in_one_service_day(engine):
    day = DAY + timedelta(20)
    sid, _ = stream(
        engine,
        ["gcp"],
        provider="gcp",
        account="gcp:project:credits",
        ba="gcp:ba:0A1B2C",
        scope="gcp:billing_export",
        vantage="gcp:table:x",
        version="gcp.v1",
    )
    kw = dict(day=day, svc="6F81", bucket="ce", key="202610")
    lines = [
        line(100, kind="gcp:cost:regular", **kw),
        line(-6, cls="discount", kind="gcp:credit:SUSTAINED_USAGE_DISCOUNT", **kw),
        line(-4, cls="discount", kind="gcp:credit:COMMITTED_USAGE_DISCOUNT", **kw),
    ]
    out = sync(engine, "gcp", sid, lines, start=day)
    assert (out.inserted, out.new_shadow_facts) == (3, 2)
    assert money(total(engine, A, day, "gcp", "ce")) == (Decimal("90.00"), "complete")


def test_23_grouping_version_switch_never_counts_two_layouts(engine):
    day = DAY + timedelta(21)
    account = f"aws:acct:{uuid.uuid4().hex[:12]}"
    v1, _ = stream(engine, ["payer"], account=account)
    v2, _ = stream(engine, ["payer"], account=account, version="aws.v2.service+record_type+usage_type")
    sync(engine, "payer", v1, [line(100, day=day)], start=day)
    sync(engine, "payer", v2, [line(60, day=day, d2="BoxUsage"), line(40, day=day, d2="EBS")], start=day)
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")
    with Session(engine) as s, s.begin():
        new = CostLedgerService(s).set_authority(
            team_id=A,
            provider="aws",
            billing_account="",
            usage_account=account,
            stream_id=v2,
            actor_user_id=ALICE,
            reason="adopt v2",
        )
    assert new == 0
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")


def test_24_payer_member_disagreement_is_quarantined(engine):
    day = DAY + timedelta(22)
    account = f"aws:acct:{uuid.uuid4().hex[:12]}"
    payer, _ = stream(engine, ["payer"], account=account)
    member, _ = stream(engine, ["member"], account=account, vantage="aws:caller:member")
    sync(engine, "payer", payer, [line(100, day=day)], start=day)
    out = sync(engine, "member", member, [line(95, day=day)], start=day)
    assert out.quarantined == 1
    assert money(total(engine, A, day)) == (Decimal("100.00"), "incomplete")
    conflict = q(engine, "SELECT id FROM cost_source_conflicts WHERE usage_account = :a AND status = 'open'", a=account)
    with Session(engine) as s, s.begin():
        CostLedgerService(s).resolve_conflict(conflict, actor_user_id=ALICE, reason="payer view is the invoice")
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")
    assert (
        q(engine, "SELECT authoritative_stream_id FROM cost_source_coverage WHERE usage_account = :a", a=account)
        == payer
    )


def test_25_authority_switching_creates_no_duplicate_facts(engine):
    day = DAY + timedelta(23)
    account = f"aws:acct:{uuid.uuid4().hex[:12]}"
    payer, _ = stream(engine, ["payer"], account=account)
    member, _ = stream(engine, ["member"], account=account, vantage="aws:caller:member")
    bill = [line(100, day=day), line(-10, day=day, cls="credit", kind="aws:Credit")]
    sync(engine, "payer", payer, bill, start=day)
    sync(engine, "member", member, bill, start=day)
    with Session(engine) as s, s.begin():
        svc = CostLedgerService(s)
        kw = dict(team_id=A, provider="aws", billing_account="", usage_account=account, actor_user_id=ALICE)
        assert svc.set_authority(stream_id=member, reason="to member", **kw) == 0
        assert svc.set_authority(stream_id=payer, reason="back to payer", **kw) == 0
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE usage_account = :a", a=account) == 2
    assert q(engine, "SELECT count(*) FROM cost_source_authority_history WHERE usage_account = :a", a=account) == 2
    assert money(total(engine, A, day)) == (Decimal("90.00"), "complete")


# 26-30: history, billing, constraints, stability, failure


def test_26_legacy_cost_snapshot_is_never_touched(engine):
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(999, day=date(2026, 10, 1))], start=date(2026, 10, 1))
    assert (
        q(engine, "SELECT cost_usd::text || source_mode || completeness FROM cost_snapshots WHERE id = :i", i=LEGACY_ID)
        == "250.00legacylegacy"
    )
    assert q(engine, "SELECT count(*) FROM cost_snapshots") == 1


def test_27_shadow_publication_creates_no_billable_usage(engine):
    # publish its own day so the checks below never pass vacuously on an empty ledger
    day = DAY + timedelta(26)
    sid, _ = stream(engine, ["payer"])
    out = sync(engine, "payer", sid, [line(70, day=day)], start=day)
    assert out.new_shadow_facts == 1
    bases = (
        "SELECT string_agg(basis || '=' || quantity, ',' ORDER BY basis) FROM billing_usage_ledger WHERE stream_id = :s"
    )
    assert q(engine, bases, s=sid) == "first_ingested=1,legacy_saved_rows=1"
    for table in ("usage_events", "usage_daily_rollups", "stripe_meter_exports"):
        assert q(engine, f"SELECT count(*) FROM {table}") == 0
    assert q(engine, "SELECT bool_and(shadow AND usage_event_id IS NULL) FROM billing_usage_ledger") is True
    assert q(engine, "SELECT bool_or(first_billable) FROM billing_canonical_facts") is False


def test_28_database_rejects_cross_tenant_references(engine):
    birch, _ = stream(engine, ["birch"], team=B)
    with pytest.raises(IntegrityError, match="fk_records_stream"):
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO cost_source_records (id, team_id, stream_id, source_kind, usage_date, line_kind, "
                    "currency, canonical_service, charge_class, amount, amount_usd, cost_bucket, last_generation) "
                    "VALUES (gen_random_uuid(), :a, :s, 'provider', :d, 'x', 'USD', 'x', 'usage', 1, 1, 'b', 1)"
                ),
                {"a": A, "s": birch, "d": DAY},
            )
    with pytest.raises(IntegrityError, match="fk_bindings_connection"):
        with engine.begin() as c:
            c.execute(
                text("INSERT INTO cost_source_stream_bindings (team_id, stream_id, connection_id) VALUES (:b, :s, :c)"),
                {"b": B, "s": birch, "c": CONN["payer"]},
            )
            c.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_29_repeated_sync_keeps_shadow_totals_and_billing_stable(engine):
    day = DAY + timedelta(24)
    sid, _ = stream(engine, ["payer"])
    bill = [line(60, day=day), line(40, day=day, svc="Amazon S3")]
    sync(engine, "payer", sid, bill, start=day)
    facts = q(engine, "SELECT count(*) FROM billing_canonical_facts")
    before = total(engine, A, day)
    for _ in range(3):
        out = sync(engine, "payer", sid, bill, start=day)
        assert (out.unchanged, out.new_shadow_facts) == (2, 0)
    assert total(engine, A, day) == before
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts") == facts
    assert q(engine, "SELECT count(*) FROM usage_events") == 0


def test_30_failed_publication_keeps_the_previous_accepted_state(engine, monkeypatch):
    day = DAY + timedelta(25)
    sid, _ = stream(engine, ["payer"])
    sync(engine, "payer", sid, [line(100, day=day)], start=day)
    observations = q(engine, "SELECT count(*) FROM cost_source_observations")

    def boom(*args, **kwargs):
        raise RuntimeError("facts store unavailable")

    monkeypatch.setattr(CostLedgerService, "_register_facts", boom)
    with pytest.raises(RuntimeError, match="facts store unavailable"):
        sync(engine, "payer", sid, [line(70, day=day)], start=day)
    monkeypatch.undo()
    assert money(total(engine, A, day)) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT count(*) FROM cost_source_observations") == observations
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
                "WHERE connection_id = :c"
            ),
            {"c": CONN["payer"]},
        )
        c.execute(
            text("UPDATE integration_sync_runs SET phase = 'failed' WHERE connection_id = :c AND phase = 'leased'"),
            {"c": CONN["payer"]},
        )


def test_off_team_cannot_publish(engine):
    sid, _ = stream(engine, ["dormant"], team=D)
    with pytest.raises(LedgerDisabled):
        sync(engine, "dormant", sid, [line(5)])
    assert q(engine, "SELECT count(*) FROM cost_source_records WHERE stream_id = :s", s=sid) == 0
