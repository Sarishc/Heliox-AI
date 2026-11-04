"""
Shadow sync orchestration on real PostgreSQL at migration head, in one disposable database per module.

Every test creates its own connection and accounts, so it can run alone or in any order. Time passing
beyond a lease is simulated by moving the lease's expiry in a separate transaction. A worker crash is a
BaseException, which nothing in the application catches.
"""

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from postgres_scratch import alembic, needs_postgres, scratch_database
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from app.integrations.ledger.aws import AwsCostExplorerAdapter
from app.integrations.ledger.azure import AzureCostManagementAdapter
from app.integrations.ledger.base import (
    VERIFIED,
    AdapterConfigError,
    DateWindow,
    Discovery,
    FetchIncomplete,
    SourcePage,
    StreamSpec,
)
from app.integrations.ledger.gcp import GcpBillingExportAdapter
from app.services.cost_ledger import CostLedgerService, LedgerFenced, RunIncomplete, normalize_line
from app.services.ledger_shadow import activation
from app.services.ledger_shadow.activation import ShadowActivationRefused, ShadowPolicy
from app.services.ledger_shadow.coverage import stream_coverage
from app.services.ledger_shadow.inventory import InventoryInvalid, configure_inventory, resolve_expected
from app.services.ledger_shadow.orchestrator import ShadowSyncOrchestrator
from app.services.ledger_shadow.recovery import reap_abandoned_runs
from app.services.ledger_shadow.staging import heartbeat, stage_page

pytestmark = needs_postgres

A, B, OFF = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
ALICE = uuid.uuid4()
LEGACY_ID = uuid.uuid4()
DAY = date(2026, 6, 10)
ENABLED = ShadowPolicy(enabled=True, env="dev")
SECRET = "SECRET-do-not-store-7f3a"
BACKEND = Path(__file__).resolve().parents[1]


class WorkerCrash(BaseException):
    """The process died here: nothing runs after this, as with a killed worker."""


@pytest.fixture(scope="module")
def engine():
    with scratch_database("heliox_ledger_shadow") as url:
        alembic(url, "upgrade", "head")
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(
                text("INSERT INTO teams (id, name) VALUES (:a, 'Acme'), (:b, 'Birch'), (:o, 'Off')"),
                {"a": A, "b": B, "o": OFF},
            )
            c.execute(
                text("INSERT INTO users (id, email, hashed_password) VALUES (:u, 'a@acme.test', 'x')"), {"u": ALICE}
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
                    "VALUES (:i, :a, '2026-05-01', 'aws', 'ec2', 250.00)"
                ),
                {"i": LEGACY_ID, "a": A},
            )
        yield eng
        eng.dispose()


def line(
    amount,
    day=DAY,
    svc="Amazon EC2",
    bucket="ec2",
    cls="usage",
    kind="aws:Usage",
    cur="USD",
    usd=None,
    fx=None,
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
        is_estimated=est,
    )


def account_id():
    return f"aws:acct:{uuid.uuid4().hex[:12]}"


def spec(account, vantage="aws:caller:payer", role="cost", ba="", provider="aws", scope="aws:linked_account"):
    return StreamSpec(
        provider=provider,
        scope_type=scope,
        billing_account=ba,
        usage_account=account,
        vantage=vantage,
        metric="UnblendedCost",
        grouping_version="aws.v1.service+record_type",
        config={"metric": "UnblendedCost"},
        role=role,
    )


class Fake:
    """A scripted adapter. A script is a list of steps per account: lines, an exception to raise, or a hook to call.

    The last list of lines is the final page. ``FetchIncomplete`` or a crash ends the script early.
    """

    provider = "aws"

    def __init__(self, scripts, specs=None, discovered=None, discover_error=None, verdicts=None):
        self.verdicts = verdicts
        self.scripts = scripts
        self.specs = specs or [spec(a) for a in scripts]
        self.discovered = discovered
        self.discover_error = discover_error
        self.calls = 0

    def streams(self):
        return self.specs

    def verify_scope(self):
        return self.verdicts if self.verdicts is not None else {x.usage_account: VERIFIED for x in self.specs}

    def discover(self, window):
        if self.discover_error:
            raise self.discover_error
        if self.discovered is None:
            return Discovery(supported=False)
        return Discovery(accounts=frozenset(self.discovered))

    def fetch(self, stream, window):
        self.calls += 1
        steps = self.scripts[stream.usage_account]
        pages = [i for i, s in enumerate(steps) if isinstance(s, (list, tuple))]
        seq = 0
        for i, step in enumerate(steps):
            if callable(step) and not isinstance(step, (list, tuple)):
                step()
            elif isinstance(step, BaseException):
                raise step
            else:
                yield SourcePage(seq, tuple(step), is_last=i == pages[-1] and i == len(steps) - 1)
                seq += 1


class Rig:
    """One connection with its declared inventory, and an orchestrator bound to a scripted adapter."""

    def __init__(self, engine, scripts, *, team=A, specs=None, connection=None, **fake):
        self.engine = engine
        self.team = team
        self.sessions = sessionmaker(bind=engine)
        self.adapter = Fake(scripts, specs, **fake)
        self.conn = connection or uuid.uuid4()
        if connection is None:
            with engine.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted, status) "
                        "VALUES (:i, :t, 'aws', :n, 'not-a-real-config', 'active')"
                    ),
                    {"i": self.conn, "t": team, "n": f"c-{self.conn.hex[:8]}"},
                )
        with self.sessions() as s, s.begin():
            self.streams = dict(
                zip(
                    [x.usage_account for x in self.adapter.specs],
                    configure_inventory(s, team, self.conn, self.adapter.specs),
                )
            )
        self.orchestrator = ShadowSyncOrchestrator(self.sessions, lambda p, c: self.adapter, ENABLED)

    def run(self, window=None, script=None):
        if script is not None:
            self.adapter.scripts = script
        run_id = self.orchestrator.create_run(self.team, self.conn, window or DateWindow(DAY, DAY + timedelta(1)))
        return run_id, self.orchestrator.execute(run_id)

    def expire(self):
        with self.engine.begin() as c:
            c.execute(
                text(
                    "UPDATE cost_sync_leases SET expires_at = clock_timestamp() - interval '1 second' WHERE connection_id = :c"
                ),
                {"c": self.conn},
            )

    def run_state(self, run_id):
        return q(
            self.engine,
            "SELECT phase || '/' || status || '/' || attempt FROM integration_sync_runs WHERE id = :r",
            r=run_id,
        )

    def lease(self):
        return q(
            self.engine,
            "SELECT coalesce(holder_attempt::text, '-') || '/' || token FROM cost_sync_leases WHERE connection_id = :c",
            c=self.conn,
        )


def q(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def total(engine, team, day=DAY, bucket="ec2", provider="aws"):
    with Session(engine) as s:
        found = [
            t
            for t in CostLedgerService(s).shadow_totals(team, [day])
            if (t.provider, t.cost_bucket) == (provider, bucket)
        ]
    return found[0] if found else None


def money(t):
    return (t.amount_usd, t.completeness)


def records(engine, stream_id):
    return q(engine, "SELECT count(*) FROM cost_source_records WHERE stream_id = :s", s=stream_id)


def staged(engine, run_id):
    return q(engine, "SELECT count(*) FROM cost_sync_staging WHERE sync_run_id = :r", r=run_id)


def observations(engine, stream_id):
    return q(
        engine,
        "SELECT count(*) FROM cost_source_observations o JOIN cost_source_records r ON r.id = o.record_id WHERE r.stream_id = :s",
        s=stream_id,
    )


def metrics(engine, run_id):
    return q(engine, "SELECT metrics_json FROM integration_sync_runs WHERE id = :r", r=run_id)


def fetched_at(engine, stream_id):
    return q(
        engine, "SELECT last_complete_fetch_at FROM cost_source_stream_checkpoints WHERE stream_id = :s", s=stream_id
    )


def checkpoint(engine, stream_id):
    return q(engine, "SELECT final_through FROM cost_source_stream_checkpoints WHERE stream_id = :s", s=stream_id)


def legacy_untouched(engine):
    assert q(engine, "SELECT cost_usd FROM cost_snapshots WHERE id = :i", i=LEGACY_ID) == Decimal("250.00")
    assert q(engine, "SELECT count(*) FROM cost_snapshots") == 1
    for table in ("usage_events", "usage_daily_rollups", "stripe_meter_exports"):
        assert q(engine, f"SELECT count(*) FROM {table}") == 0


# The whole path


def test_complete_run_publishes_and_finishes_atomically(engine):
    account = account_id()
    rig = Rig(engine, {account: [[line(60)], [line(40, svc="Amazon S3")]]})
    run_id, result = rig.run()
    sid = rig.streams[account]
    assert result.status == "published"
    assert rig.run_state(run_id) == "published/success/1"
    assert rig.lease() == "-/1"
    assert records(engine, sid) == 2
    assert money(total(engine, A)) is not None
    assert q(engine, "SELECT status FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id) == "published"
    assert (
        q(engine, "SELECT authoritative_stream_id FROM cost_source_coverage WHERE usage_account = :a", a=account) == sid
    )
    assert checkpoint(engine, sid) is None  # no starting boundary is stored; see test_ledger_shadow_corrections
    assert fetched_at(engine, sid) is not None
    assert staged(engine, run_id) == 0  # temporary by design, gone once the run is terminal
    report = metrics(engine, run_id)["ledger"]["inventory"]
    assert report["expected"] == report["fetched"] == report["published"] == report["authoritative"] == [account]
    assert report["missing"] == report["failed"] == report["incomplete"] == report["unknown"] == []
    assert "records_saved" not in json.dumps(metrics(engine, run_id))
    legacy_untouched(engine)


def test_the_same_bill_ten_times_stays_the_same(engine):
    day, account = DAY + timedelta(1), account_id()
    rig = Rig(engine, {account: [[line(100, day=day, bucket="repeat")]]})
    window = DateWindow(day, day + timedelta(1))
    for _ in range(10):
        _, result = rig.run(window)
        assert result.status == "published"
    assert money(total(engine, A, day, "repeat")) == (Decimal("100.00"), "complete")
    assert records(engine, rig.streams[account]) == 1
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE usage_account = :a", a=account) == 1
    assert observations(engine, rig.streams[account]) == 10  # one inserted, nine confirmations


def test_a_provider_correction_replaces_the_amount(engine):
    day, account = DAY + timedelta(2), account_id()
    rig = Rig(engine, {account: [[line(100, day=day, bucket="fix")]]})
    window = DateWindow(day, day + timedelta(1))
    rig.run(window)
    _, result = rig.run(window, {account: [[line(80, day=day, bucket="fix")]]})
    assert result.status == "published"
    assert money(total(engine, A, day, "fix")) == (Decimal("80.00"), "complete")
    assert (
        q(
            engine,
            "SELECT string_agg(o.change_kind, ',' ORDER BY o.generation) FROM cost_source_observations o "
            "JOIN cost_source_records r ON r.id = o.record_id WHERE r.stream_id = :s",
            s=rig.streams[account],
        )
        == "inserted,corrected"
    )


def test_negative_credits_and_different_accounts_add_up(engine):
    day = DAY + timedelta(3)
    window = DateWindow(day, day + timedelta(1))
    first, second = account_id(), account_id()
    rig = Rig(
        engine,
        {
            first: [
                [line(100, day=day, bucket="net"), line(-15, day=day, bucket="net", cls="credit", kind="aws:Credit")]
            ],
            second: [[line(25, day=day, bucket="net")]],
        },
    )
    _, result = rig.run(window)
    assert result.status == "published"
    assert money(total(engine, A, day, "net")) == (Decimal("110.00"), "complete")


# Crashes


def test_crash_during_pagination_publishes_nothing_and_a_retry_finishes(engine):
    day, account = DAY + timedelta(4), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(60, day=day, bucket="crash1")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    sid = rig.streams[account]
    assert rig.run_state(run_id) == "fetching/running/1"
    assert (records(engine, sid), staged(engine, run_id), checkpoint(engine, sid)) == (0, 1, None)
    assert (
        q(engine, "SELECT status FROM cost_sync_run_streams WHERE sync_run_id = :r AND attempt = 1", r=run_id)
        == "fetching"
    )
    assert total(engine, A, day, "crash1") is None
    # The first page alone never advanced anything. Once the lease expires, a new attempt fetches again.
    rig.expire()
    rig.adapter.scripts = {
        account: [[line(60, day=day, bucket="crash1")], [line(40, day=day, bucket="crash1", svc="S3")]]
    }
    result = rig.orchestrator.execute(run_id)
    assert result.status == "published"
    assert rig.run_state(run_id) == "published/success/2"
    assert money(total(engine, A, day, "crash1")) == (Decimal("100.00"), "complete")
    assert (
        q(
            engine,
            "SELECT string_agg(attempt || ':' || status, ',' ORDER BY attempt) FROM cost_sync_run_streams WHERE sync_run_id = :r",
            r=run_id,
        )
        == "1:fenced,2:published"
    )


def test_crash_after_staging_causes_no_double_accounting(engine, monkeypatch):
    day, account = DAY + timedelta(5), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(100, day=day, bucket="crash2")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)

    def crash(*args, **kwargs):
        raise WorkerCrash()

    monkeypatch.setattr(ShadowSyncOrchestrator, "_publish", crash)
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    monkeypatch.undo()
    assert records(engine, rig.streams[account]) == 0
    assert q(engine, "SELECT status FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id) == "complete"
    rig.expire()
    assert rig.orchestrator.execute(run_id).status == "published"
    assert money(total(engine, A, day, "crash2")) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE usage_account = :a", a=account) == 1


def test_crash_before_commit_leaves_no_partial_publication(engine, monkeypatch):
    day = DAY + timedelta(6)
    window = DateWindow(day, day + timedelta(1))
    first, second = account_id(), account_id()
    rig = Rig(engine, {first: [[line(70, day=day, bucket="crash3")]], second: [[line(30, day=day, bucket="crash3")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)

    def crash(*args, **kwargs):
        raise WorkerCrash()

    monkeypatch.setattr(CostLedgerService, "finish_run", crash)  # after every publish, inside the transaction
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    monkeypatch.undo()
    for account in (first, second):
        sid = rig.streams[account]
        assert (records(engine, sid), checkpoint(engine, sid)) == (0, None)
        assert q(engine, "SELECT count(*) FROM cost_source_stream_days WHERE stream_id = :s", s=sid) == 0
    assert q(engine, "SELECT count(*) FROM billing_usage_ledger WHERE sync_run_id = :r", r=run_id) == 0
    assert staged(engine, run_id) == 2  # still there: nothing was accepted
    rig.expire()
    assert rig.orchestrator.execute(run_id).status == "published"
    assert money(total(engine, A, day, "crash3")) == (Decimal("100.00"), "complete")


def test_crash_after_commit_before_acknowledgment_is_a_no_op_on_redelivery(engine):
    day, account = DAY + timedelta(7), account_id()
    rig = Rig(engine, {account: [[line(100, day=day, bucket="crash4")]]})
    run_id, result = rig.run(DateWindow(day, day + timedelta(1)))
    assert result.status == "published"
    before = (observations(engine, rig.streams[account]), rig.run_state(run_id), rig.lease())
    fetches = rig.adapter.calls
    redelivered = rig.orchestrator.execute(run_id)  # the broker never saw the acknowledgment
    assert (redelivered.status, redelivered.retryable) == ("already_terminal", False)
    assert rig.adapter.calls == fetches
    assert (observations(engine, rig.streams[account]), rig.run_state(run_id), rig.lease()) == before
    assert money(total(engine, A, day, "crash4")) == (Decimal("100.00"), "complete")


# Delivery, leases and fencing


def test_duplicate_delivery_while_running_is_refused_by_the_lease(engine):
    day, account = DAY + timedelta(8), account_id()
    window = DateWindow(day, day + timedelta(1))
    entered, release = threading.Event(), threading.Event()

    def wait():
        entered.set()
        assert release.wait(10)

    rig = Rig(engine, {account: [wait, [line(100, day=day, bucket="dup")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    results = {}
    worker = threading.Thread(target=lambda: results.update(first=rig.orchestrator.execute(run_id)))
    worker.start()
    assert entered.wait(10)
    second = rig.orchestrator.execute(run_id)  # another worker, in its own transactions
    assert (second.status, second.retryable) == ("busy", True)
    assert rig.run_state(run_id) == "fetching/running/1"  # no attempt consumed
    release.set()
    worker.join()
    assert results["first"].status == "published"
    assert money(total(engine, A, day, "dup")) == (Decimal("100.00"), "complete")
    assert observations(engine, rig.streams[account]) == 1


def test_create_run_is_idempotent_while_a_run_is_in_flight(engine):
    day, account = DAY + timedelta(9), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    ids = []
    threads = [
        threading.Thread(target=lambda: ids.append(rig.orchestrator.create_run(rig.team, rig.conn, window)))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ids) == 4 and len(set(ids)) == 1
    assert q(engine, "SELECT count(*) FROM integration_sync_runs WHERE connection_id = :c", c=rig.conn) == 1
    manifest = metrics(engine, ids[0])["ledger"]["manifest"]
    assert manifest["window"] == {"start": day.isoformat(), "end": (day + timedelta(1)).isoformat()}
    assert [s["usage_account"] for s in manifest["streams"]] == [account]


def test_task_retry_with_the_same_run_uses_a_newer_attempt(engine):
    day, account = DAY + timedelta(10), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(
        engine, {account: [[line(5, day=day, bucket="retry")], FetchIncomplete("provider_page_failed", retryable=True)]}
    )
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    first = rig.orchestrator.execute(run_id)
    assert (first.status, first.retryable, first.reason) == ("retry", True, "provider_page_failed")
    sid = rig.streams[account]
    assert records(engine, sid) == 0
    assert rig.lease() == "-/1"  # released, so the retry need not wait for expiry
    assert rig.run_state(run_id) == "fetching/running/1"
    rig.adapter.scripts = {account: [[line(5, day=day, bucket="retry")]]}
    assert rig.orchestrator.execute(run_id).status == "published"
    assert rig.run_state(run_id) == "published/success/2"
    trail = metrics(engine, run_id)["ledger"]["recovery"]
    assert [(e["event"], e["attempt"]) for e in trail] == [("attempt_failed_retrying", 1)]
    assert (
        q(
            engine,
            "SELECT string_agg(attempt || ':' || status || ':' || coalesce(error_code, ''), ',' ORDER BY attempt) "
            "FROM cost_sync_run_streams WHERE sync_run_id = :r",
            r=run_id,
        )
        == "1:failed:provider_page_failed,2:published:"
    )


def test_lease_takeover_fences_the_stale_worker_during_fetch(engine):
    day, account = DAY + timedelta(11), account_id()
    window = DateWindow(day, day + timedelta(1))
    new_results = {}

    def lose_the_lease():
        # Worker A paused past its lease. Worker B takes over and completes the run.
        rig.expire()
        rig.adapter.scripts = {account: [[line(200, day=day, bucket="takeover")]]}
        new_results["b"] = rig.orchestrator.execute(run_id)
        rig.adapter.scripts = script_a

    script_a = {
        account: [
            [line(1, day=day, bucket="takeover")],
            lose_the_lease,
            [line(2, day=day, bucket="takeover", svc="S3")],
        ]
    }
    rig = Rig(engine, script_a)
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    stale = rig.orchestrator.execute(run_id)
    assert new_results["b"].status == "published"
    assert (stale.status, stale.reason) == ("fenced", "lease_lost")
    assert rig.run_state(run_id) == "published/success/2"
    assert money(total(engine, A, day, "takeover")) == (Decimal("200.00"), "complete")
    assert records(engine, rig.streams[account]) == 1


def test_stale_worker_cannot_publish_after_losing_its_lease(engine, monkeypatch):
    day, account = DAY + timedelta(12), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(100, day=day, bucket="stale")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    original = ShadowSyncOrchestrator._publish

    def lose_then_publish(self, *args, **kwargs):
        rig.expire()  # between validation and publication
        return original(self, *args, **kwargs)

    monkeypatch.setattr(ShadowSyncOrchestrator, "_publish", lose_then_publish)
    result = rig.orchestrator.execute(run_id)
    monkeypatch.undo()
    assert (result.status, result.reason) == ("fenced", "lease_lost")
    assert records(engine, rig.streams[account]) == 0
    assert q(engine, "SELECT count(*) FROM billing_usage_ledger WHERE stream_id = :s", s=rig.streams[account]) == 0
    assert rig.run_state(run_id) == "fetching/running/1"  # still recoverable


def test_stale_token_is_rejected_when_staging_and_heartbeating(engine):
    day, account = DAY + timedelta(13), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with rig.sessions() as s, s.begin():
        token = CostLedgerService(s).acquire_lease(run_id, 1)
        s.execute(text("UPDATE integration_sync_runs SET phase = 'fetching' WHERE id = :r"), {"r": run_id})
    for bad_attempt, bad_token in ((1, token + 1), (2, token)):
        with pytest.raises(LedgerFenced):
            with rig.sessions() as s, s.begin():
                heartbeat(s, run_id, bad_attempt, bad_token)
    rig.expire()
    with pytest.raises(LedgerFenced):  # an expired lease is never revived, even with the right token
        with rig.sessions() as s, s.begin():
            heartbeat(s, run_id, 1, token)
    assert staged(engine, run_id) == 0
    assert (
        q(engine, "SELECT expires_at < clock_timestamp() FROM cost_sync_leases WHERE connection_id = :c", c=rig.conn)
        is True
    )


def test_page_retries_are_idempotent_and_conflicting_pages_are_detected(engine):
    day, account = DAY + timedelta(14), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    sid = rig.streams[account]
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with rig.sessions() as s, s.begin():
        CostLedgerService(s).acquire_lease(run_id, 1)
        s.execute(
            text(
                "INSERT INTO cost_sync_run_streams (sync_run_id, connection_id, attempt, team_id, stream_id, window_start, "
                "window_end, status) VALUES (:r, :c, 1, :t, :s, :a, :b, 'pending')"
            ),
            {"r": run_id, "c": rig.conn, "t": A, "s": sid, "a": day, "b": day + timedelta(1)},
        )
    page = SourcePage(0, (line(10, day=day),))
    for _ in range(3):  # the same page delivered again
        with rig.sessions() as s, s.begin():
            stage_page(s, run_id, 1, sid, page)
    assert staged(engine, run_id) == 1
    assert (
        q(
            engine,
            "SELECT staged_rows || '/' || pages || '/' || staged_total_usd::numeric(10,2) FROM cost_sync_run_streams WHERE sync_run_id = :r",
            r=run_id,
        )
        == "1/1/10.00"
    )
    from app.services.ledger_shadow.staging import StagingConflict

    with pytest.raises(StagingConflict):
        with rig.sessions() as s, s.begin():
            stage_page(s, run_id, 1, sid, SourcePage(1, (line(11, day=day),)))
    assert q(engine, "SELECT amount FROM cost_sync_staging WHERE sync_run_id = :r", r=run_id) == Decimal("10")


def test_conflicting_pages_never_publish(engine):
    day, account = DAY + timedelta(15), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(10, day=day, bucket="conflict")], [line(11, day=day, bucket="conflict")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("retry", "conflicting_page")
    assert records(engine, rig.streams[account]) == 0


# Inventory


def test_failed_expected_account_blocks_run_completeness_and_is_not_zero(engine):
    day = DAY + timedelta(16)
    window = DateWindow(day, day + timedelta(1))
    good, missing = account_id(), account_id()
    rig = Rig(
        engine,
        {good: [[line(100, day=day, bucket="inv")]], missing: [FetchIncomplete("subscription_inaccessible")]},
    )
    run_id, result = rig.run(window)
    assert result.status == "partial"
    assert rig.run_state(run_id) == "partial/partial/1"
    report = metrics(engine, run_id)["ledger"]["inventory"]
    assert report["missing"] == [missing] and report["published"] == [good] and report["incomplete"] == [missing]
    assert q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["stream_errors"] == {
        missing: "subscription_inaccessible"
    }
    with Session(engine) as s:
        days = {c.usage_account: c for c in CostLedgerService(s).coverage_completeness(A, [day])}
    assert days[good].financial_state == "complete"
    assert missing not in days  # no row at all: absent, never a confirmed zero
    assert q(engine, "SELECT count(*) FROM cost_source_stream_days WHERE stream_id = :s", s=rig.streams[missing]) == 0
    assert checkpoint(engine, rig.streams[missing]) is None


def test_complete_inventory_confirms_a_zero_cost_account(engine):
    day = DAY + timedelta(17)
    window = DateWindow(day, day + timedelta(1))
    busy, quiet = account_id(), account_id()
    rig = Rig(engine, {busy: [[line(10, day=day, bucket="zero")]], quiet: [[]]})
    run_id, result = rig.run(window)
    assert result.status == "published"
    with Session(engine) as s:
        days = {c.usage_account: c for c in CostLedgerService(s).coverage_completeness(A, [day])}
    assert (days[quiet].financial_state, days[quiet].converted_total_usd) == ("complete", Decimal("0"))
    assert fetched_at(engine, rig.streams[quiet]) is not None


def test_an_account_with_no_final_page_is_not_a_zero(engine):
    day, account = DAY + timedelta(18), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: []})  # the fetch ended without ever declaring completion
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("retry", "no_final_page")
    assert q(engine, "SELECT count(*) FROM cost_source_stream_days WHERE stream_id = :s", s=rig.streams[account]) == 0


def test_unknown_accounts_are_reported_and_block_a_full_success(engine):
    day, account = DAY + timedelta(19), account_id()
    window = DateWindow(day, day + timedelta(1))
    surprise = account_id()
    rig = Rig(engine, {account: [[line(5, day=day, bucket="unk")]]}, discovered=[account, surprise])
    run_id, result = rig.run(window)
    assert result.status == "partial"
    report = metrics(engine, run_id)["ledger"]["inventory"]
    assert (report["unknown"], report["discovery"]) == ([surprise], "complete")
    assert q(engine, "SELECT count(*) FROM cost_source_streams WHERE usage_account = :a", a=surprise) == 0


def test_inventory_is_declared_not_derived_from_rows(engine):
    day, account = DAY + timedelta(20), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    window = DateWindow(day, day + timedelta(1))
    # Configuration now expects a second account that was never bound: drift blocks the run before any fetch
    rig.adapter.specs = [spec(account), spec(account_id())]
    with pytest.raises(InventoryInvalid) as err:
        rig.orchestrator.create_run(rig.team, rig.conn, window)
    assert err.value.code == "inventory_drift"
    rig.adapter.specs = []
    with pytest.raises(InventoryInvalid) as err:
        rig.orchestrator.create_run(rig.team, rig.conn, window)
    assert err.value.code == "inventory_empty"
    assert q(engine, "SELECT count(*) FROM integration_sync_runs WHERE connection_id = :c", c=rig.conn) == 0
    assert rig.adapter.calls == 0


def test_inventory_change_after_the_run_was_requested_ends_it_with_a_reason(engine):
    day, account = DAY + timedelta(21), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    rig.adapter.specs = [spec(account), spec(account_id())]
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", "inventory_drift")
    assert rig.run_state(run_id) == "failed/failed/0"
    assert (
        q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id)["reason"]
        == "inventory_drift"
    )
    assert rig.adapter.calls == 0


# Reaper


def test_reaper_leaves_an_active_worker_alone(engine):
    day, account = DAY + timedelta(22), account_id()
    window = DateWindow(day, day + timedelta(1))
    seen = {}

    def reap_during_fetch():
        with rig.sessions() as s, s.begin():
            seen["actions"] = reap_abandoned_runs(s)

    rig = Rig(engine, {account: [reap_during_fetch, [line(10, day=day, bucket="active")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    assert rig.orchestrator.execute(run_id).status == "published"
    assert [a for a in seen["actions"] if a.run_id == run_id] == []
    assert "recovery" not in metrics(engine, run_id)["ledger"]
    assert money(total(engine, A, day, "active")) == (Decimal("10.00"), "complete")


def test_reaper_requeues_an_abandoned_attempt_without_declaring_the_fetch_failed(engine):
    day, account = DAY + timedelta(23), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(60, day=day, bucket="reap")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    rig.expire()
    with rig.sessions() as s, s.begin():
        actions = [a for a in reap_abandoned_runs(s) if a.run_id == run_id]
    assert [(a.action, a.reason) for a in actions] == [("requeue", "lease_expired")]
    assert (
        rig.run_state(run_id) == "fetching/running/1"
    )  # not failed: an expired lease proves nothing about the provider
    assert rig.lease() == "-/1"
    assert staged(engine, run_id) == 1  # evidence of the attempt is kept until the run is terminal
    assert (
        q(engine, "SELECT status || ':' || error_code FROM cost_sync_run_streams WHERE sync_run_id = :r", r=run_id)
        == "fenced:attempt_abandoned"
    )
    assert [e["event"] for e in metrics(engine, run_id)["ledger"]["recovery"]] == ["lease_expired_requeued"]
    rig.adapter.scripts = {account: [[line(100, day=day, bucket="reap")]]}
    assert rig.orchestrator.execute(run_id).status == "published"
    assert money(total(engine, A, day, "reap")) == (Decimal("100.00"), "complete")
    assert staged(engine, run_id) == 0


def test_reaper_ends_a_run_with_no_attempts_left(engine):
    day, account = DAY + timedelta(24), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(60, day=day, bucket="exhaust")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with engine.begin() as c:
        c.execute(text("UPDATE integration_sync_runs SET max_attempts = 1 WHERE id = :r"), {"r": run_id})
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    rig.expire()
    with rig.sessions() as s, s.begin():
        actions = [a for a in reap_abandoned_runs(s) if a.run_id == run_id]
    assert [(a.action, a.reason) for a in actions] == [("abandoned", "attempts_exhausted")]
    assert rig.run_state(run_id) == "abandoned/failed/1"
    assert q(engine, "SELECT error_details FROM integration_sync_runs WHERE id = :r", r=run_id) == {
        "reason": "attempts_exhausted",
        "attempt": 1,
    }
    assert rig.lease() == "-/1"
    assert (staged(engine, run_id), records(engine, rig.streams[account])) == (0, 0)
    assert metrics(engine, run_id)["ledger"]["recovery"][-1]["event"] == "terminated"
    assert rig.orchestrator.execute(run_id).status == "already_terminal"


def test_reaper_expires_a_run_that_was_never_dispatched(engine):
    day, account = DAY + timedelta(25), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, DateWindow(day, day + timedelta(1)))
    with rig.sessions() as s, s.begin():
        assert [a for a in reap_abandoned_runs(s) if a.run_id == run_id] == []  # still within its deadline
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE integration_sync_runs SET dispatch_deadline_at = clock_timestamp() - interval '1 minute' WHERE id = :r"
            ),
            {"r": run_id},
        )
    with rig.sessions() as s, s.begin():
        assert [a.action for a in reap_abandoned_runs(s) if a.run_id == run_id] == ["dispatch_expired"]
    assert rig.run_state(run_id) == "dispatch_expired/failed/0"


def test_reaper_skips_a_run_a_worker_has_locked_and_a_retry_wins_the_race(engine):
    day, account = DAY + timedelta(26), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(60, day=day, bucket="race")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    rig.expire()
    holder = rig.sessions()
    holder.begin()
    holder.execute(text("SELECT 1 FROM integration_sync_runs WHERE id = :r FOR UPDATE"), {"r": run_id})
    started = time.monotonic()
    with rig.sessions() as s, s.begin():
        actions = reap_abandoned_runs(s)
    assert time.monotonic() - started < 2  # it skipped rather than waited
    assert [a for a in actions if a.run_id == run_id] == []
    holder.rollback()
    holder.close()
    # The retry claims the run first. Now the lease is live, so a reaper pass changes nothing.
    rig.adapter.scripts = {account: [lambda: _reap_and_check(rig, run_id), [line(100, day=day, bucket="race")]]}
    assert rig.orchestrator.execute(run_id).status == "published"
    assert rig.run_state(run_id) == "published/success/2"
    assert money(total(engine, A, day, "race")) == (Decimal("100.00"), "complete")


def _reap_and_check(rig, run_id):
    with rig.sessions() as s, s.begin():
        assert [a for a in reap_abandoned_runs(s) if a.run_id == run_id] == []


# Checkpoints and staleness


def test_checkpoint_is_rolled_back_with_a_failed_publication(engine, monkeypatch):
    day, account = DAY + timedelta(27), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(10, day=day, bucket="cp")]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    import app.services.ledger_shadow.orchestrator as orchestrator_module

    original = orchestrator_module.record_complete_fetch

    def record_then_die(*args, **kwargs):
        original(*args, **kwargs)
        raise WorkerCrash()

    monkeypatch.setattr(orchestrator_module, "record_complete_fetch", record_then_die)
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    monkeypatch.undo()
    sid = rig.streams[account]
    assert q(engine, "SELECT count(*) FROM cost_source_stream_checkpoints WHERE stream_id = :s", s=sid) == 0
    assert records(engine, sid) == 0


def test_checkpoint_stops_at_estimated_days_and_never_moves_backwards(engine):
    day, account = DAY + timedelta(28), account_id()
    second = day + timedelta(1)
    window = DateWindow(day, day + timedelta(2))
    rig = Rig(engine, {account: [[line(10, day=day, bucket="cp2"), line(9, day=second, bucket="cp2", est=True)]]})
    rig.run(window)
    sid = rig.streams[account]

    def final_through():
        with rig.sessions() as s:
            return stream_coverage(s, sid, window).final_through

    assert final_through() == day  # the estimated day is not final
    assert money(total(engine, A, second, "cp2")) == (Decimal("9.00"), "estimated")
    rig.run(window, {account: [[line(10, day=day, bucket="cp2"), line(9, day=second, bucket="cp2")]]})
    assert final_through() == second
    fetched = fetched_at(engine, sid)
    rig.run(DateWindow(day, day + timedelta(1)), {account: [[line(10, day=day, bucket="cp2")]]})
    assert final_through() == second  # republishing an earlier day leaves it where it was
    assert fetched_at(engine, sid) >= fetched  # the stored fetch time only moves forward
    assert checkpoint(engine, sid) is None


def test_an_older_fetch_never_overwrites_a_newer_accepted_result(engine):
    day, account = DAY + timedelta(29), account_id()
    window = DateWindow(day, day + timedelta(1))
    results = {}

    def newer_fetch_finishes_first():
        other = Rig(engine, {account: [[line(80, day=day, bucket="older")]]})
        _, results["newer"] = other.run(window)

    rig = Rig(engine, {account: [newer_fetch_finishes_first, [line(100, day=day, bucket="older")]]})
    _, older = rig.run(window)
    assert results["newer"].status == "published"
    assert older.status == "published"
    assert money(total(engine, A, day, "older")) == (Decimal("80.00"), "complete")


# Financial invariants


def test_overlapping_views_never_double_count_and_witness_only_is_not_zero(engine):
    day, account = DAY + timedelta(30), account_id()
    window = DateWindow(day, day + timedelta(1))
    payer = Rig(engine, {account: [[line(100, day=day, bucket="view")]]})
    member = Rig(
        engine, {account: [[line(100, day=day, bucket="view")]]}, specs=[spec(account, vantage="aws:caller:member")]
    )
    # The member view arrives first with a configured authority: unknown, not zero
    with payer.sessions() as s, s.begin():
        CostLedgerService(s).set_authority(
            team_id=A,
            provider="aws",
            billing_account="",
            usage_account=account,
            stream_id=payer.streams[account],
            actor_user_id=ALICE,
            reason="payer is the invoice",
        )
    _, result = member.run(window)
    assert result.status == "published"
    assert metrics(engine, _)["ledger"]["inventory"]["witness"] == [account]
    t = total(engine, A, day, "view")
    assert (t.amount_usd, t.completeness, t.uncovered) == (None, "incomplete", 1)
    payer.run(window)
    assert money(total(engine, A, day, "view")) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT count(*) FROM billing_canonical_facts WHERE usage_account = :a", a=account) == 1
    # The configured authority was never replaced, however the views arrived
    assert (
        q(engine, "SELECT stream_id FROM cost_source_authority WHERE usage_account = :a", a=account)
        == payer.streams[account]
    )
    assert q(engine, "SELECT count(*) FROM cost_source_authority_history WHERE usage_account = :a", a=account) == 1


def test_a_disagreeing_or_misclassified_witness_is_quarantined(engine):
    day = DAY + timedelta(31)
    window = DateWindow(day, day + timedelta(1))
    account = account_id()
    payer = Rig(engine, {account: [[line(100, day=day, bucket="cls-a")]]})
    member = Rig(
        engine,
        {account: [[line(100, day=day, bucket="cls-b", svc="Amazon S3")]]},
        specs=[spec(account, vantage="aws:caller:member")],
    )
    payer.run(window)
    member.run(window)
    with Session(engine) as s:
        [c] = [c for c in CostLedgerService(s).coverage_completeness(A, [day]) if c.usage_account == account]
    assert (c.fetch_state, c.financial_state, c.open_conflicts, c.classification_conflicts) == (
        "conflict",
        "incomplete",
        1,
        1,
    )
    assert money(total(engine, A, day, "cls-a")) == (Decimal("100.00"), "incomplete")
    b = total(engine, A, day, "cls-b")
    assert (b.amount_usd, b.completeness) == (None, "incomplete")


def test_unconverted_cost_stays_financially_incomplete(engine):
    day, account = DAY + timedelta(32), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(50, day=day, bucket="fx", cur="EUR")]]})
    run_id, result = rig.run(window)
    assert result.status == "published"  # the fetch was complete
    assert fetched_at(engine, rig.streams[account]) is not None  # the checkpoint row is about the fetch
    with Session(engine) as s:
        [c] = [c for c in CostLedgerService(s).coverage_completeness(A, [day]) if c.usage_account == account]
    assert (c.fetch_state, c.financial_state, c.unconverted_count) == ("final", "incomplete", 1)
    t = total(engine, A, day, "fx")
    assert (t.amount_usd, t.completeness) == (None, "incomplete")


def test_a_failed_fetch_retires_nothing(engine):
    day, account = DAY + timedelta(33), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(100, day=day, bucket="keep"), line(40, day=day, bucket="keep", svc="S3")]]})
    rig.run(window)
    _, result = rig.run(window, {account: [[line(100, day=day, bucket="keep")], FetchIncomplete("access_denied")]})
    assert result.status == "failed"
    assert money(total(engine, A, day, "keep")) == (Decimal("140.00"), "complete")
    assert (
        q(
            engine,
            "SELECT count(*) FROM cost_source_records WHERE stream_id = :s AND state = 'absent'",
            s=rig.streams[account],
        )
        == 0
    )


# Tenancy, secrets, activation


def test_tags_and_labels_never_move_cost_to_another_team(engine):
    day, account = DAY + timedelta(34), account_id()
    window = DateWindow(day, day + timedelta(1))
    tagged = normalize_line(
        usage_date=day,
        line_kind="aws:Usage",
        canonical_service="Amazon EC2",
        charge_class="usage",
        cost_bucket="tags",
        currency="USD",
        amount=Decimal("100"),
        dim_1="Amazon EC2",
        dim_2="Team$Birch",
    )
    rig = Rig(engine, {account: [[tagged]]})
    rig.run(window)
    assert q(engine, "SELECT team_id FROM cost_source_records WHERE stream_id = :s", s=rig.streams[account]) == A
    assert total(engine, B, day, "tags") is None


def test_a_connection_cannot_publish_another_teams_stream(engine):
    day, account = DAY + timedelta(35), account_id()
    birch = Rig(engine, {account: [[line(1, day=day)]]}, team=B)
    acme = Rig(engine, {account_id(): [[line(1, day=day)]]})
    # Acme's connection cannot be bound to Birch's stream: the composite key refuses it
    with pytest.raises(DBAPIError):
        with acme.sessions() as s, s.begin():
            s.execute(
                text("INSERT INTO cost_source_stream_bindings (team_id, stream_id, connection_id) VALUES (:t, :s, :c)"),
                {"t": B, "s": birch.streams[account], "c": acme.conn},
            )
            s.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    # Even when asked to resolve another team's bindings, an inventory crossing teams is refused
    with acme.sessions() as s, pytest.raises(InventoryInvalid) as err:
        resolve_expected(s, A, birch.conn, birch.adapter.specs)
    assert err.value.code == "inventory_tenant_mismatch"
    assert records(engine, birch.streams[account]) == 0


def test_secrets_never_reach_the_database_or_logs(engine, caplog):
    day, account = DAY + timedelta(36), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [RuntimeError(f"auth failed with token={SECRET}")]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with caplog.at_level(logging.DEBUG):
        result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("retry", "fetch_error")
    assert SECRET not in caplog.text
    with engine.connect() as c:
        for table in ("integration_sync_runs", "cost_sync_run_streams", "cost_sync_staging", "cost_source_streams"):
            assert SECRET not in str(c.execute(text(f"SELECT * FROM {table}")).all())


@pytest.mark.parametrize(
    "policy,code",
    [
        (ShadowPolicy(enabled=False, env="dev"), "worker_disabled"),
        (ShadowPolicy(enabled=True, env="production"), "environment_not_permitted"),
    ],
)
def test_environment_gates_refuse_before_touching_anything(engine, policy, code):
    day, account = DAY + timedelta(37), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    closed = ShadowSyncOrchestrator(rig.sessions, lambda p, c: rig.adapter, policy)
    result = closed.execute(run_id)
    assert (result.status, result.reason) == ("disabled", code)
    assert rig.run_state(run_id) == "queued/running/0"
    assert rig.adapter.calls == 0
    with pytest.raises(ShadowActivationRefused) as err:
        closed.create_run(rig.team, rig.conn, window)
    assert err.value.code == code


def test_a_team_not_in_shadow_mode_is_refused_and_never_enrolled(engine):
    day, account = DAY + timedelta(38), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]}, team=OFF)
    with pytest.raises(ShadowActivationRefused) as err:
        rig.orchestrator.create_run(rig.team, rig.conn, DateWindow(day, day + timedelta(1)))
    assert err.value.code == "team_not_in_shadow_mode"
    assert q(engine, "SELECT count(*) FROM team_cost_ledger_settings WHERE team_id = :o", o=OFF) == 0
    assert rig.adapter.calls == 0


def test_team_leaving_shadow_mode_stops_a_queued_run(engine):
    team = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id, name) VALUES (:t, 'Leaving')"), {"t": team})
        c.execute(
            text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, 'shadow')"), {"t": team}
        )
    day, account = DAY + timedelta(39), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]}, team=team)
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, DateWindow(day, day + timedelta(1)))
    with engine.begin() as c:
        c.execute(text("UPDATE team_cost_ledger_settings SET ledger_mode = 'off' WHERE team_id = :t"), {"t": team})
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", "team_not_in_shadow_mode")
    assert records(engine, rig.streams[account]) == 0


def test_live_mode_stays_impossible_and_the_schema_check_needs_every_gate(engine, monkeypatch):
    with pytest.raises(DBAPIError, match="ck_ledger_settings_gate_no_live"):
        with engine.begin() as c:
            c.execute(text("UPDATE team_cost_ledger_settings SET ledger_mode = 'live' WHERE team_id = :a"), {"a": A})
    with Session(engine) as s:
        activation.verify_ledger_schema(s)
    monkeypatch.setattr(activation, "REQUIRED_GATES", (*activation.REQUIRED_GATES, "ck_a_gate_that_is_missing"))
    with Session(engine) as s, pytest.raises(ShadowActivationRefused) as err:
        activation.verify_ledger_schema(s)
    assert err.value.code == "ledger_schema_invalid"


def test_no_billing_side_effects_and_legacy_connection_state_is_untouched(engine, monkeypatch):
    import app.utils.usage_metering as metering

    def forbidden(*args, **kwargs):
        raise AssertionError("legacy ingestion billing must not be called")

    monkeypatch.setattr(metering, "record_ingestion_event", forbidden)
    day, account = DAY + timedelta(40), account_id()
    rig = Rig(engine, {account: [[line(100, day=day, bucket="bill")]]})
    run_id, result = rig.run(DateWindow(day, day + timedelta(1)))
    assert result.status == "published"
    legacy_untouched(engine)
    assert q(
        engine,
        "SELECT last_sync_at IS NULL AND last_successful_sync_at IS NULL FROM integration_connections WHERE id = :c",
        c=rig.conn,
    )
    assert q(
        engine,
        "SELECT bool_and(shadow AND usage_event_id IS NULL) FROM billing_usage_ledger WHERE stream_id = :s",
        s=rig.streams[account],
    )
    assert (
        q(engine, "SELECT bool_or(first_billable) FROM billing_canonical_facts WHERE usage_account = :a", a=account)
        is False
    )


# Real adapters through the whole path, with fake provider clients


def aws_response(day, amount):
    return {
        "ResultsByTime": [
            {
                "TimePeriod": {"Start": day.isoformat(), "End": (day + timedelta(1)).isoformat()},
                "Estimated": False,
                "Total": {},
                "Groups": [
                    {"Keys": ["Amazon EC2", "Usage"], "Metrics": {"UnblendedCost": {"Amount": amount, "Unit": "USD"}}}
                ],
            }
        ]
    }


class AwsClients:
    def __init__(self, caller, day, amount):
        self.caller, self.day, self.amount = caller, day, amount

    def __call__(self, service):
        return self

    def get_caller_identity(self):
        return {"Account": self.caller}

    def get_cost_and_usage(self, **kwargs):
        return aws_response(self.day, self.amount)

    def get_dimension_values(self, **kwargs):
        return {"DimensionValues": [{"Value": a} for a in ("111111111111",)]}

    def describe_organization(self):
        return {"Organization": {"MasterAccountId": "111111111111"}}

    def list_accounts(self, **kwargs):
        return {"Accounts": [{"Id": i, "State": "ACTIVE"} for i in ("111111111111", "222222222222")]}


def rig_with(engine, adapter, team=A):
    rig = Rig(engine, {}, team=team, specs=list(adapter.streams()))
    rig.adapter = adapter
    rig.orchestrator = ShadowSyncOrchestrator(rig.sessions, lambda p, c: adapter, ENABLED)
    return rig


def test_aws_payer_and_member_views_of_one_account_count_once(engine):
    day = DAY + timedelta(41)
    window = DateWindow(day, day + timedelta(1))
    config = {"payer_account_id": "111111111111", "linked_account_ids": ["111111111111"]}
    team = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id, name) VALUES (:t, 'AwsE2E')"), {"t": team})
        c.execute(
            text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, 'shadow')"), {"t": team}
        )
    payer = rig_with(
        engine, AwsCostExplorerAdapter(config, client_factory=AwsClients("111111111111", day, "100")), team
    )
    member = rig_with(
        engine, AwsCostExplorerAdapter(config, client_factory=AwsClients("222222222222", day, "100")), team
    )
    run_id, result = payer.run(window)
    assert result.status == "published"
    assert money(total(engine, team, day, "ec2")) == (Decimal("100.00"), "complete")
    # A member caller cannot see the payer account: its stream is inaccessible, so it adds nothing
    _, result = member.run(window)
    assert result.status == "failed"
    assert money(total(engine, team, day, "ec2")) == (Decimal("100.00"), "complete")
    assert q(engine, "SELECT count(*) FROM cost_source_records WHERE team_id = :t", t=team) == 1


class GcpClient:
    def __init__(self, rows):
        self.rows = rows
        self.sql = ""

    def __call__(self):
        return self

    def query(self, sql, job_config=None):
        self.sql = sql
        return self

    def result(self):
        if self.sql.startswith("SELECT MAX(export_time)"):
            pages = [[{"last_export": datetime(2026, 10, 1, tzinfo=timezone.utc)}]]
        elif "DISTINCT project.id" in self.sql:
            pages = [[]]
        elif "project.id IS NULL" in self.sql:
            pages = [[]]
        else:
            pages = [self.rows]

        class Rows:
            total_rows = sum(len(p) for p in pages)

        rows = Rows()
        rows.pages = iter(pages)
        return rows


def gcp_adapter(rows, table="gcp_billing_export_v1_0A1B2C_3D4E5F_6A7B8C"):
    return GcpBillingExportAdapter(
        {
            "gcp_project_id": "billing-admin-1",
            "bigquery_dataset": "billing_export",
            "billing_export_table": table,
            "billing_account_id": "0A1B2C-3D4E5F-6A7B8C",
            "project_ids": ["ml-prod-1"],
        },
        client_factory=GcpClient(rows),
        parameters=lambda v: v,
        project_billing_info=lambda project: {
            "billingAccountName": "billingAccounts/0A1B2C-3D4E5F-6A7B8C",
            "billingEnabled": True,
        },
        today=lambda: date(2026, 10, 1),
    )


def gcp_rows(day, cost, credit=None):
    base = dict(
        usage_day=day,
        service_id="6F81",
        service_name="gcp-compute",
        currency="USD",
        invoice_month="202606",
        rate_min=Decimal("1"),
        rate_max=Decimal("1"),
        last_export=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    rows = [dict(base, line_type="cost", sub_type="regular", amount=Decimal(cost))]
    if credit:
        rows.append(dict(base, line_type="credit", sub_type="PROMOTION", amount=Decimal(credit)))
    return rows


def test_gcp_credits_late_corrections_and_copied_exports(engine):
    day = DAY + timedelta(42)
    window = DateWindow(day, day + timedelta(1))
    team = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id, name) VALUES (:t, 'GcpE2E')"), {"t": team})
        c.execute(
            text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, 'shadow')"), {"t": team}
        )
    main = rig_with(engine, gcp_adapter(gcp_rows(day, "100", "-10")), team)
    _, result = main.run(window)
    assert result.status == "published"
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("90.00"), "complete")
    # A late-arriving correction in the export replaces the earlier values on the next deterministic re-fetch
    main.adapter = gcp_adapter(gcp_rows(day, "120", "-10"))
    main.orchestrator = ShadowSyncOrchestrator(main.sessions, lambda p, c: main.adapter, ENABLED)
    main.run(window)
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("110.00"), "complete")
    # A copied export table is a separate witness, not a second charge
    copy = rig_with(engine, gcp_adapter(gcp_rows(day, "120", "-10"), table="gcp_billing_export_v1"), team)
    _, result = copy.run(window)
    assert result.status == "published"
    assert money(total(engine, team, day, "gcp-compute", "gcp")) == (Decimal("110.00"), "complete")
    assert q(engine, "SELECT count(*) FROM cost_source_conflicts WHERE team_id = :t", t=team) == 0


SUB_OK = "11111111-1111-1111-1111-111111111111"
SUB_GONE = "22222222-2222-2222-2222-222222222222"


def azure_adapter(day, config=None, gone=()):
    def handler(request):
        body = request.read().decode()
        if any(s in str(request.url) or s in body for s in gone):
            return httpx.Response(403)
        if request.method == "GET" and "billingSubscriptions" in str(request.url):
            return httpx.Response(
                200, json={"value": [{"properties": {"subscriptionId": x}} for x in (SUB_OK, SUB_GONE)]}
            )
        if request.method == "GET":
            return httpx.Response(200, json={"state": "Enabled"})
        if json.loads(body)["dataset"]["grouping"] == [{"type": "Dimension", "name": "SubscriptionId"}]:
            return httpx.Response(
                200,
                json={"properties": {"columns": [{"name": "SubscriptionId"}], "rows": [[SUB_OK], [SUB_GONE]]}},
            )
        return httpx.Response(
            200,
            json={
                "properties": {
                    "columns": [
                        {"name": n} for n in ("Cost", "CostUSD", "UsageDate", "ServiceName", "ChargeType", "Currency")
                    ],
                    "rows": [[54, 54, int(day.strftime("%Y%m%d")), "Virtual Machines", "Usage", "USD"]],
                }
            },
        )

    return AzureCostManagementAdapter(
        {"subscription_ids": [SUB_OK, SUB_GONE], **(config or {})},
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        token_provider=lambda force: "token",
        sleep=lambda s: None,
        today=lambda: date(2026, 10, 1),
    )


def test_azure_partial_scope_success_never_marks_the_source_complete_and_overlap_counts_once(engine):
    day = DAY + timedelta(43)
    window = DateWindow(day, day + timedelta(1))
    team = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO teams (id, name) VALUES (:t, 'AzureE2E')"), {"t": team})
        c.execute(
            text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, 'shadow')"), {"t": team}
        )
    subs = rig_with(engine, azure_adapter(day, gone=(SUB_GONE,)), team)
    run_id, result = subs.run(window)
    assert result.status == "partial"
    assert subs.run_state(run_id) == "partial/partial/1"
    report = metrics(engine, run_id)["ledger"]["inventory"]
    assert report["missing"] == [f"azure:sub:{SUB_GONE}"]
    assert report["published"] == [f"azure:sub:{SUB_OK}"]
    assert money(total(engine, team, day, "azure_vm", "azure")) == (Decimal("54.00"), "complete")
    # An overlapping billing-account scope from another connection observes the same subscription: a witness.
    # It is the first to publish the other subscription, so that one is covered too: 54 + 54, never 54 * 3.
    billing = rig_with(
        engine,
        azure_adapter(day, {"billing_account_id": "BA-1", "use_billing_account_scope": True}),
        team,
    )
    assert "BA-1" in billing.adapter.streams()[0].vantage
    _, result = billing.run(window)
    assert result.status == "published"
    assert money(total(engine, team, day, "azure_vm", "azure")) == (Decimal("108.00"), "complete")
    assert (
        q(
            engine,
            "SELECT authoritative_stream_id FROM cost_source_coverage WHERE team_id = :t AND usage_account = :a",
            t=team,
            a=f"azure:sub:{SUB_OK}",
        )
        == subs.streams[f"azure:sub:{SUB_OK}"]
    )
    assert q(engine, "SELECT count(*) FROM cost_source_conflicts WHERE team_id = :t", t=team) == 0


def test_adapter_config_error_ends_the_run_without_fetching(engine):
    day, account = DAY + timedelta(44), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, DateWindow(day, day + timedelta(1)))

    def bad_config(provider, config):
        raise AdapterConfigError("invalid_linked_accounts")

    broken = ShadowSyncOrchestrator(rig.sessions, bad_config, ENABLED)
    result = broken.execute(run_id)
    assert (result.status, result.reason) == ("failed", "invalid_linked_accounts")
    assert rig.run_state(run_id) == "failed/failed/0"


def test_concurrent_runs_for_two_connections_of_one_team_both_count(engine):
    day = DAY + timedelta(45)
    window = DateWindow(day, day + timedelta(1))
    first, second = account_id(), account_id()
    one = Rig(engine, {first: [[line(60, day=day, bucket="both")]]})
    two = Rig(engine, {second: [[line(25, day=day, bucket="both")]]})
    results = {}
    threads = [
        threading.Thread(target=lambda: results.update(one=one.run(window)[1])),
        threading.Thread(target=lambda: results.update(two=two.run(window)[1])),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert (results["one"].status, results["two"].status) == ("published", "published")
    assert money(total(engine, A, day, "both")) == (Decimal("85.00"), "complete")


def test_finish_run_partial_needs_a_publication(engine):
    day, account = DAY + timedelta(46), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, DateWindow(day, day + timedelta(1)))
    with rig.sessions() as s, s.begin():
        token = CostLedgerService(s).acquire_lease(run_id, 1)
    with pytest.raises(RunIncomplete):
        with rig.sessions() as s, s.begin():
            CostLedgerService(s).finish_run(run_id, attempt=1, fencing_token=token, status="partial")
    assert rig.run_state(run_id) == "leased/running/1"


# Activation in a real process


def _celery_tasks(**env):
    code = (
        "from app.celery_app import celery_app\n"
        "print(sorted(t for t in celery_app.tasks if t.startswith('ledger.')))\n"
        "print(sorted(str(v['task']) for v in celery_app.conf.beat_schedule.values() if 'ledger' in str(v['task'])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-500:]
    return result.stdout.strip().splitlines()[-2:]


def test_worker_is_not_registered_by_default_and_is_never_scheduled():
    assert _celery_tasks(LEDGER_SHADOW_WORKER_ENABLED="false") == ["[]", "[]"]
    assert _celery_tasks(LEDGER_SHADOW_WORKER_ENABLED="true") == [
        "['ledger.reap_abandoned_runs', 'ledger.shadow_sync']",
        "[]",
    ]


def test_task_retries_with_bounded_backoff_and_returns_the_outcome(monkeypatch):
    from celery.exceptions import Retry

    from app.tasks import ledger_shadow_tasks as tasks
    from app.services.ledger_shadow.orchestrator import RunResult

    for retries in range(10):
        assert 15 <= tasks.backoff_seconds(retries) <= tasks.BACKOFF_CAP_SECONDS
    run_id = str(uuid.uuid4())
    monkeypatch.setattr(tasks.ShadowSyncOrchestrator, "execute", lambda self, r: RunResult("busy", retryable=True))
    monkeypatch.setattr(tasks.ShadowSyncOrchestrator, "__init__", lambda self, sessions: None)
    countdowns = []

    def fake_retry(countdown=None, **kwargs):
        countdowns.append(countdown)
        return Retry()

    monkeypatch.setattr(tasks.run_shadow_sync, "retry", fake_retry)
    tasks.run_shadow_sync.push_request(retries=0)
    try:
        with pytest.raises(Retry):
            tasks.run_shadow_sync.run(run_id)
    finally:
        tasks.run_shadow_sync.pop_request()
    assert len(countdowns) == 1 and countdowns[0] >= 15
    monkeypatch.setattr(tasks.ShadowSyncOrchestrator, "execute", lambda self, r: RunResult("already_terminal"))
    assert tasks.run_shadow_sync.run(run_id)["status"] == "already_terminal"


def test_an_attempt_past_the_limit_ends_the_run_with_a_reason(engine):
    day, account = DAY + timedelta(47), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(5, day=day, bucket="limit")], WorkerCrash()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with engine.begin() as c:
        c.execute(text("UPDATE integration_sync_runs SET max_attempts = 1 WHERE id = :r"), {"r": run_id})
    with pytest.raises(WorkerCrash):
        rig.orchestrator.execute(run_id)
    rig.expire()
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.reason) == ("failed", "attempts_exhausted")
    assert rig.run_state(run_id) == "failed/failed/1"
    assert rig.lease() == "-/1"
    assert (staged(engine, run_id), records(engine, rig.streams[account])) == (0, 0)


def test_a_retryable_failure_on_the_last_attempt_publishes_only_complete_streams(engine):
    day = DAY + timedelta(48)
    window = DateWindow(day, day + timedelta(1))
    good, flaky = account_id(), account_id()
    rig = Rig(
        engine,
        {
            good: [[line(30, day=day, bucket="last")]],
            flaky: [[line(70, day=day, bucket="last")], FetchIncomplete("provider_unavailable", retryable=True)],
        },
    )
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    with engine.begin() as c:
        c.execute(text("UPDATE integration_sync_runs SET max_attempts = 1 WHERE id = :r"), {"r": run_id})
    result = rig.orchestrator.execute(run_id)
    assert result.status == "partial"
    assert rig.run_state(run_id) == "partial/partial/1"
    assert money(total(engine, A, day, "last")) == (Decimal("30.00"), "complete")
    assert records(engine, rig.streams[flaky]) == 0  # its first page was never accepted
    assert staged(engine, run_id) == 0


def test_cancellation_during_a_fetch_publishes_nothing_and_stays_recoverable(engine):
    from celery.exceptions import SoftTimeLimitExceeded

    day, account = DAY + timedelta(49), account_id()
    window = DateWindow(day, day + timedelta(1))
    rig = Rig(engine, {account: [[line(5, day=day, bucket="cancel")], SoftTimeLimitExceeded()]})
    run_id = rig.orchestrator.create_run(rig.team, rig.conn, window)
    result = rig.orchestrator.execute(run_id)
    assert (result.status, result.retryable) == ("retry", True)
    assert records(engine, rig.streams[account]) == 0
    assert rig.run_state(run_id) == "fetching/running/1"
    rig.adapter.scripts = {account: [[line(5, day=day, bucket="cancel")]]}
    assert rig.orchestrator.execute(run_id).status == "published"


def test_legacy_runs_are_invisible_to_the_worker_and_the_reaper(engine):
    day, account = DAY + timedelta(50), account_id()
    rig = Rig(engine, {account: [[line(1, day=day)]]})
    legacy = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO integration_sync_runs (id, connection_id, started_at, status, triggered_by) "
                "VALUES (:i, :c, now() - interval '2 days', 'running', 'scheduled')"
            ),
            {"i": legacy, "c": rig.conn},
        )
    assert rig.orchestrator.execute(legacy).status == "not_found"
    with rig.sessions() as s, s.begin():
        assert [a for a in reap_abandoned_runs(s) if a.run_id == legacy] == []
    assert (
        q(
            engine,
            "SELECT status || '/' || pipeline || '/' || coalesce(phase, '-') FROM integration_sync_runs WHERE id = :i",
            i=legacy,
        )
        == "running/legacy/-"
    )
