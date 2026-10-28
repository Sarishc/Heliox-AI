"""
SSE connection lifecycle: leased slots, cleanup on every exit path, and a
Redis subscriber that waits for messages instead of spinning.

The slot-accounting tests need a real Redis (the admission step is a Lua
script). They use HELIOX_TEST_REDIS_URL, or REDIS_URL when running in CI, and
are skipped otherwise. Never point HELIOX_TEST_REDIS_URL at a shared Redis.
"""

import asyncio
import os
import threading
import time
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.api.routes import events as events_route
from app.core import events


def _test_redis_url():
    if os.environ.get("HELIOX_TEST_REDIS_URL"):
        return os.environ["HELIOX_TEST_REDIS_URL"]
    if os.environ.get("CI"):
        return os.environ.get("REDIS_URL")
    return None


@pytest.fixture
def real_redis(monkeypatch):
    import redis

    url = _test_redis_url()
    if not url:
        pytest.skip("set HELIOX_TEST_REDIS_URL to a disposable Redis to run slot-accounting tests")
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except Exception as exc:
        pytest.skip(f"test Redis unreachable: {exc}")
    monkeypatch.setattr(events, "get_redis", lambda: client)
    teams = []

    def new_team():
        team = f"test-{uuid4().hex}"
        teams.append(team)
        return team

    yield client, new_team
    for team in teams:
        client.delete(f"{events.CONN_LEASE_PREFIX}{team}")


# ── Slot accounting (real Redis) ─────────────────────────────────────────────


def test_concurrent_admission_never_exceeds_limit(real_redis):
    _, new_team = real_redis
    team = new_team()
    barrier = threading.Barrier(20)
    results = []

    def connect():
        barrier.wait()
        results.append(events.acquire_conn_slot(team, uuid4().hex))

    threads = [threading.Thread(target=connect) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count(True) == events.MAX_CONNS_PER_TEAM
    assert results.count(False) == 20 - events.MAX_CONNS_PER_TEAM
    assert events.get_conn_count(team) == events.MAX_CONNS_PER_TEAM


def test_release_frees_the_slot(real_redis):
    _, new_team = real_redis
    team = new_team()
    conns = [uuid4().hex for _ in range(events.MAX_CONNS_PER_TEAM)]
    assert all(events.acquire_conn_slot(team, c) for c in conns)
    assert events.acquire_conn_slot(team, uuid4().hex) is False
    events.release_conn_slot(team, conns[0])
    assert events.acquire_conn_slot(team, uuid4().hex) is True


def test_renewing_a_held_slot_does_not_take_another(real_redis):
    _, new_team = real_redis
    team = new_team()
    conns = [uuid4().hex for _ in range(events.MAX_CONNS_PER_TEAM)]
    assert all(events.acquire_conn_slot(team, c) for c in conns)
    assert events.acquire_conn_slot(team, conns[2]) is True  # renewal while full
    assert events.get_conn_count(team) == events.MAX_CONNS_PER_TEAM


def test_crashed_connections_expire_with_their_lease(real_redis, monkeypatch):
    _, new_team = real_redis
    monkeypatch.setattr(events, "CONN_LEASE_SECONDS", 1)
    team = new_team()
    assert all(events.acquire_conn_slot(team, uuid4().hex) for _ in range(events.MAX_CONNS_PER_TEAM))
    assert events.acquire_conn_slot(team, uuid4().hex) is False
    time.sleep(1.3)  # nobody renewed: a crashed worker
    assert events.get_conn_count(team) == 0
    assert events.acquire_conn_slot(team, uuid4().hex) is True


def test_long_lived_connection_is_not_forgotten(real_redis, monkeypatch):
    _, new_team = real_redis
    monkeypatch.setattr(events, "CONN_LEASE_SECONDS", 1)
    team = new_team()
    me = uuid4().hex
    assert events.acquire_conn_slot(team, me)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:  # outlives the lease 3x, renewing like the SSE ping
        assert events.acquire_conn_slot(team, me) is True
        time.sleep(0.4)
    assert events.get_conn_count(team) == 1
    others = [events.acquire_conn_slot(team, uuid4().hex) for _ in range(events.MAX_CONNS_PER_TEAM)]
    assert others.count(True) == events.MAX_CONNS_PER_TEAM - 1


def test_reload_cycles_do_not_accumulate(real_redis):
    _, new_team = real_redis
    team = new_team()
    for _ in range(25):
        conn = uuid4().hex
        assert events.acquire_conn_slot(team, conn) is True
        events.release_conn_slot(team, conn)
    assert events.get_conn_count(team) == 0


def test_redis_unavailable_is_reported_not_admitted(monkeypatch):
    monkeypatch.setattr(events, "get_redis", lambda: None)
    assert events.acquire_conn_slot("team", "conn") is None
    assert events.get_conn_count("team") == 0
    events.release_conn_slot("team", "conn")  # never raises


# ── Route behaviour ──────────────────────────────────────────────────────────


@pytest.fixture
def stream_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    team = uuid4()
    app.dependency_overrides[events_route._resolve_team_id] = lambda: team
    monkeypatch.setattr("app.core.rate_limit.is_rate_limited", lambda *a, **k: (False, 60))
    calls = {"acquire": [], "release": []}
    yield TestClient(app, raise_server_exceptions=False), calls, str(team)
    app.dependency_overrides.clear()


def _slots(monkeypatch, calls, results):
    results = iter(results)

    def acquire(team_id, conn_id):
        calls["acquire"].append(conn_id)
        return next(results)

    monkeypatch.setattr(events_route, "acquire_conn_slot", acquire)
    monkeypatch.setattr(events_route, "release_conn_slot", lambda team_id, conn_id: calls["release"].append(conn_id))


async def _closing_subscriber(channel, queue, stop_event):
    await queue.put(None)


def test_stream_releases_its_slot_when_it_ends(stream_client, monkeypatch):
    client, calls, _ = stream_client
    _slots(monkeypatch, calls, [True])
    with patch.object(events_route, "_redis_subscriber", side_effect=_closing_subscriber):
        resp = client.get("/api/v1/events/stream")
    assert resp.status_code == 200
    assert resp.text.startswith(": connected\nretry: 5000\n\n")
    assert "no-transform" in resp.headers["cache-control"]
    assert calls["release"] == calls["acquire"][:1]


def test_full_team_gets_429_and_takes_no_slot(stream_client, monkeypatch):
    client, calls, _ = stream_client
    _slots(monkeypatch, calls, [False])
    resp = client.get("/api/v1/events/stream")
    assert resp.status_code == 429
    assert calls["release"] == []


def test_redis_unavailable_gets_503(stream_client, monkeypatch):
    client, calls, _ = stream_client
    _slots(monkeypatch, calls, [None])
    assert client.get("/api/v1/events/stream").status_code == 503


def test_subscriber_error_still_releases(stream_client, monkeypatch):
    client, calls, _ = stream_client
    _slots(monkeypatch, calls, [True])

    async def _broken(channel, queue, stop_event):
        raise RuntimeError("redis exploded")

    async def _gen(team_id, queue, stop_event):
        yield ": connected\n\n"
        raise RuntimeError("generator failed")

    with (
        patch.object(events_route, "_redis_subscriber", side_effect=_broken),
        patch.object(events_route, "_sse_generator", side_effect=_gen),
    ):
        client.get("/api/v1/events/stream")
    assert len(calls["release"]) == 1


def test_lost_lease_with_full_team_ends_the_stream(stream_client, monkeypatch):
    client, calls, _ = stream_client
    _slots(monkeypatch, calls, [True, False])  # admitted, then renewal finds the team full
    monkeypatch.setattr(events_route, "PING_INTERVAL_SECONDS", 0)

    async def _quiet(channel, queue, stop_event):
        await stop_event.wait()

    with patch.object(events_route, "_redis_subscriber", side_effect=_quiet):
        resp = client.get("/api/v1/events/stream")
    assert resp.status_code == 200
    assert len(calls["acquire"]) == 2 and calls["acquire"][0] == calls["acquire"][1]
    assert calls["release"] == calls["acquire"][:1]


# ── Subscriber loop ──────────────────────────────────────────────────────────


class _FakePubSub:
    def __init__(self):
        self.timeouts = []
        self.unsubscribed = self.closed = False

    async def subscribe(self, channel):
        pass

    async def get_message(self, ignore_subscribe_messages=False, timeout=0.0):
        self.timeouts.append(timeout)
        # like redis-py: returns at once when timeout is 0, otherwise waits for it
        await asyncio.sleep(timeout or 0)
        return None

    async def unsubscribe(self, channel):
        self.unsubscribed = True

    async def aclose(self):
        self.closed = True


class _FakeAsyncRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        pass


async def test_subscriber_waits_for_messages_instead_of_spinning():
    pubsub = _FakePubSub()
    queue: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    with patch("redis.asyncio.from_url", return_value=_FakeAsyncRedis(pubsub)):
        task = asyncio.create_task(events_route._redis_subscriber("heliox:events:t", queue, stop))
        await asyncio.sleep(0.5)
        stop.set()
        await asyncio.wait_for(task, timeout=3)
    assert len(pubsub.timeouts) <= 3, f"{len(pubsub.timeouts)} polls in 0.5 s"
    assert all(t and t >= 0.5 for t in pubsub.timeouts)
    assert pubsub.unsubscribed and pubsub.closed
