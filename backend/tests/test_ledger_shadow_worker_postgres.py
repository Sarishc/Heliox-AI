"""
The real task wrappers, then a real Celery worker and Redis broker, against a disposable PostgreSQL database.

No provider is contacted. The worker runs the real ``ledger.shadow_sync`` and ``ledger.reap_abandoned_runs`` tasks
with a fake adapter (see ledger_worker_app). It is never given a Beat schedule.
"""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import redis
from ledger_worker_fake import ConfiguredAdapter
from postgres_scratch import alembic, needs_postgres, scratch_database
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from test_ledger_shadow_orchestration_postgres import ENABLED, Fake, line, spec

from app.integrations.ledger.base import DateWindow
from app.services.cost_ledger import CostLedgerService
from app.services.ledger_shadow.activation import ShadowPolicy
from app.services.ledger_shadow.inventory import configure_inventory
from app.services.ledger_shadow.orchestrator import ShadowSyncOrchestrator

pytestmark = needs_postgres

TEAM = uuid.uuid4()
DAY = date(2026, 5, 4)
BACKEND = Path(__file__).resolve().parents[1]
WINDOW = DateWindow(DAY, DAY + timedelta(1))


@pytest.fixture(scope="module")
def database():
    with scratch_database("heliox_ledger_worker") as url:
        alembic(url, "upgrade", "head")
        eng = create_engine(url)
        with eng.begin() as c:
            c.execute(text("INSERT INTO teams (id, name) VALUES (:t, 'Worker')"), {"t": TEAM})
            c.execute(
                text("INSERT INTO team_cost_ledger_settings (team_id, ledger_mode) VALUES (:t, 'shadow')"), {"t": TEAM}
            )
        yield url, eng
        eng.dispose()


def make_connection(engine, config):
    connection = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO integration_connections (id, team_id, provider, name, config_encrypted, status) "
                "VALUES (:i, :t, 'aws', :n, :cfg, 'active')"
            ),
            {"i": connection, "t": TEAM, "n": connection.hex[:10], "cfg": config},
        )
    return connection


def q(engine, sql, **params):
    with engine.connect() as c:
        return c.execute(text(sql), params).scalar()


def run_state(engine, run):
    return q(engine, "SELECT phase || '/' || status || '/' || attempt FROM integration_sync_runs WHERE id = :r", r=run)


def total(engine, day):
    with Session(engine) as s:
        found = [t for t in CostLedgerService(s).shadow_totals(TEAM, [day]) if t.cost_bucket == "worker"]
    return (found[0].amount_usd, found[0].completeness) if found else None


# The task wrappers, through Celery's task machinery, with no broker


@pytest.fixture
def wrappers(database, monkeypatch):
    """The real task module with its database and adapter pointed at the test's."""
    _, eng = database
    from app.services.ledger_shadow import orchestrator as module
    from app.tasks import ledger_shadow_tasks as tasks

    monkeypatch.setattr(tasks, "SessionLocal", sessionmaker(bind=eng))
    monkeypatch.setattr(ShadowPolicy, "from_settings", classmethod(lambda cls: ENABLED))
    return tasks, module, eng


def scripted_run(eng, monkeypatch, module, script_for, day):
    account = f"aws:acct:{uuid.uuid4().hex[:12]}"
    adapter = Fake({account: script_for(account, day)})
    connection = make_connection(eng, "not-a-real-config")
    sessions = sessionmaker(bind=eng)
    with sessions() as s, s.begin():
        configure_inventory(s, TEAM, connection, adapter.specs)
    monkeypatch.setattr(module, "_default_adapter", lambda provider, config: adapter)
    run = ShadowSyncOrchestrator(sessions, policy=ENABLED).create_run(
        TEAM, connection, DateWindow(day, day + timedelta(1))
    )
    return account, adapter, connection, run


def test_task_wrapper_publishes_and_redelivery_is_a_no_op(wrappers, monkeypatch):
    tasks, module, eng = wrappers
    day = DAY + timedelta(1)
    _, adapter, _, run = scripted_run(eng, monkeypatch, module, lambda a, d: [[line(100, day=d, bucket="worker")]], day)
    first = tasks.run_shadow_sync.apply(args=[str(run)]).get()
    assert first == {"run_id": str(run), "status": "published", "reason": None}
    assert run_state(eng, run) == "published/success/1"
    second = tasks.run_shadow_sync.apply(args=[str(run)]).get()
    assert second["status"] == "already_terminal"
    assert total(eng, day) == (Decimal("100.00"), "complete")
    assert adapter.calls == 1


def test_task_wrapper_retries_a_recoverable_failure_with_a_new_attempt(wrappers, monkeypatch):
    from app.integrations.ledger.base import FetchIncomplete

    tasks, module, eng = wrappers
    day = DAY + timedelta(2)
    account, adapter, _, run = scripted_run(
        eng,
        monkeypatch,
        module,
        lambda a, d: [[line(1, day=d, bucket="worker")], FetchIncomplete("provider_unavailable", retryable=True)],
        day,
    )
    original_fetch = adapter.fetch
    good = [[line(100, day=day, bucket="worker")]]

    def fail_once(stream, window):
        if adapter.calls >= 1:
            adapter.scripts = {account: good}
        return original_fetch(stream, window)

    adapter.fetch = fail_once
    result = tasks.run_shadow_sync.apply(args=[str(run)]).get()  # eager retries run in place, without the countdown
    assert result["status"] == "published"
    assert run_state(eng, run) == "published/success/2"
    assert total(eng, day) == (Decimal("100.00"), "complete")


def test_reaper_task_requeues_after_commit_and_stays_quiet_when_disabled(wrappers, monkeypatch):
    tasks, module, eng = wrappers
    day = DAY + timedelta(3)
    _, _, connection, run = scripted_run(
        eng, monkeypatch, module, lambda a, d: [[line(1, day=d, bucket="worker")]], day
    )
    sessions = sessionmaker(bind=eng)
    with sessions() as s, s.begin():
        CostLedgerService(s).acquire_lease(run, 1)
    with eng.begin() as c:
        c.execute(
            text(
                "UPDATE cost_sync_leases SET expires_at = clock_timestamp() - interval '1 second' WHERE connection_id = :c"
            ),
            {"c": connection},
        )
    sent = []

    def recording_delay(run_id):
        # The reaper's transaction has committed by now: a separate session already sees the released lease
        sent.append(
            (run_id, q(eng, "SELECT holder_run_id FROM cost_sync_leases WHERE connection_id = :c", c=connection))
        )

    monkeypatch.setattr(tasks.run_shadow_sync, "delay", recording_delay)
    outcome = tasks.reap_abandoned_runs.apply().get()
    assert outcome["status"] == "ok" and "requeue" in outcome["actions"]
    assert (str(run), None) in sent
    monkeypatch.setattr(ShadowPolicy, "from_settings", classmethod(lambda cls: ShadowPolicy(False, "dev")))
    assert tasks.reap_abandoned_runs.apply().get() == {"status": "disabled", "reason": "worker_disabled"}
    monkeypatch.setattr(ShadowPolicy, "from_settings", classmethod(lambda cls: ShadowPolicy(True, "production")))
    assert tasks.reap_abandoned_runs.apply().get()["reason"] == "environment_not_permitted"
    # The worker task honours the same switch, and writes nothing
    assert tasks.run_shadow_sync.apply(args=[str(run)]).get()["status"] == "disabled"
    assert run_state(eng, run).startswith("leased/")


# A real worker and broker


@pytest.fixture
def broker():
    url = os.environ.get("REDIS_URL", "")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        client.ping()
    except Exception:
        if os.environ.get("HELIOX_REQUIRE_POSTGRES_TESTS") == "1":
            pytest.fail("a Redis broker is required for the worker test when PostgreSQL tests are mandatory")
        pytest.skip("no Redis broker")
    queue = f"ledger-test-{uuid.uuid4().hex[:10]}"
    yield url, queue, client
    client.delete(queue)
    client.close()


def start_worker(database_url, broker_url, queue):
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "REDIS_URL": broker_url,
        "ENV": "dev",
        "LEDGER_SHADOW_WORKER_ENABLED": "true",
        "LEDGER_TEST_QUEUE": queue,
        "PYTHONPATH": f"{BACKEND}:{BACKEND / 'tests'}",
    }
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "ledger_worker_app:celery_app",
            "worker",
            "--pool=solo",
            "-Q",
            queue,
            "--without-gossip",
            "--without-mingle",
            "--without-heartbeat",
            "--loglevel=WARNING",
            f"--hostname=ledger-test-{queue}@localhost",
        ],
        cwd=BACKEND,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for(condition, seconds=120, what="condition"):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(0.25)
    raise AssertionError(f"timed out waiting for {what}")


def sender(broker_url, queue):
    from celery import Celery

    client = Celery("ledger-test-sender", broker=broker_url)
    return lambda name, args=(): client.send_task(name, args=list(args), queue=queue)


def request_run(eng, config):
    connection = make_connection(eng, config)
    adapter = ConfiguredAdapter(config)
    sessions = sessionmaker(bind=eng)
    with sessions() as s, s.begin():
        configure_inventory(s, TEAM, connection, adapter.streams())
    orchestrator = ShadowSyncOrchestrator(sessions, lambda p, c: adapter, ENABLED)
    return connection, orchestrator.create_run(
        TEAM,
        connection,
        DateWindow(
            date.fromisoformat(json.loads(config)["day"]), date.fromisoformat(json.loads(config)["day"]) + timedelta(1)
        ),
    )


def account_config(day, **extra):
    return json.dumps(
        {"account": f"aws:acct:{uuid.uuid4().hex[:12]}", "day": day.isoformat(), "amount": "100", **extra}
    )


def test_real_worker_publishes_and_a_duplicate_delivery_changes_nothing(database, broker):
    url, eng = database
    broker_url, queue, _ = broker
    day = DAY + timedelta(10)
    _, run = request_run(eng, account_config(day))
    send = sender(broker_url, queue)
    send("ledger.shadow_sync", [str(run)])
    send("ledger.shadow_sync", [str(run)])
    worker = start_worker(url, broker_url, queue)
    try:
        wait_for(lambda: run_state(eng, run) == "published/success/1", what="the run to publish")
        wait_for(lambda: _queue_empty(broker), what="the duplicate to be consumed")
    finally:
        worker.terminate()
        worker.wait(30)
    assert total(eng, day) == (Decimal("100.00"), "complete")
    assert (
        q(
            eng,
            "SELECT count(*) FROM cost_source_observations o JOIN integration_sync_runs r ON r.id = o.sync_run_id WHERE r.id = :r",
            r=run,
        )
        == 1
    )
    assert q(eng, "SELECT count(*) FROM usage_events") == 0


def _queue_empty(broker):
    _, queue, client = broker
    return client.llen(queue) == 0


def test_real_worker_killed_mid_fetch_is_recovered_by_the_reaper_task(database, broker):
    url, eng = database
    broker_url, queue, _ = broker
    day = DAY + timedelta(11)
    with tempfile.TemporaryDirectory() as tmp:
        marker = Path(tmp) / "started"
        connection, run = request_run(eng, account_config(day, hold_once=str(marker)))
        send = sender(broker_url, queue)
        send("ledger.shadow_sync", [str(run)])
        worker = start_worker(url, broker_url, queue)
        try:
            wait_for(marker.exists, what="the worker to start fetching")
            worker.send_signal(signal.SIGKILL)  # no cleanup runs
        finally:
            worker.wait(30)
        assert run_state(eng, run) == "fetching/running/1"
        assert (
            q(eng, "SELECT count(*) FROM cost_source_records WHERE team_id = :t AND usage_date = :d", t=TEAM, d=day)
            == 0
        )
        # The lease is still live: a reaper pass leaves it alone
        replacement = start_worker(url, broker_url, queue)
        try:
            send("ledger.reap_abandoned_runs")
            wait_for(lambda: _queue_empty(broker), what="the reaper task")
            time.sleep(1)
            assert run_state(eng, run) == "fetching/running/1"
            with eng.begin() as c:
                c.execute(
                    text(
                        "UPDATE cost_sync_leases SET expires_at = clock_timestamp() - interval '1 second' "
                        "WHERE connection_id = :c"
                    ),
                    {"c": connection},
                )
            send("ledger.reap_abandoned_runs")  # it requeues the run through the real broker
            wait_for(lambda: run_state(eng, run) == "published/success/2", what="the recovered run to publish")
        finally:
            replacement.terminate()
            replacement.wait(30)
    assert total(eng, day) == (Decimal("100.00"), "complete")
    trail = q(eng, "SELECT metrics_json FROM integration_sync_runs WHERE id = :r", r=run)["ledger"]["recovery"]
    assert [e["event"] for e in trail] == ["lease_expired_requeued"]


def test_spec_helper_stays_compatible_with_the_worker_adapter():
    config = account_config(DAY)
    assert ConfiguredAdapter(config).streams()[0].identity(TEAM).provider == spec("aws:acct:x").provider
