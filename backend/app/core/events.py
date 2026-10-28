"""Redis-backed event bus for real-time SSE fan-out.

Channel pattern:  heliox:events:{team_id}          — live pub/sub
History key:      heliox:events:history:{team_id}  — sorted set, last 100 events
Read set:         heliox:events:read:{team_id}     — set of read event_ids
Connection slots: heliox:events:conn_leases:{team_id} — sorted set, member = connection id,
                  score = lease expiry (Redis server time). Admission is one Lua script,
                  so concurrent connects can't exceed the limit; each SSE ping renews the
                  lease, and a crashed worker's slots expire after CONN_LEASE_SECONDS.
                  (The old heliox:events:conns:* integer counters expire within 60 s.)

Publishing is synchronous (fire-and-forget via the existing redis-py client)
so it never blocks a Celery task or FastAPI handler.  The SSE endpoint
subscribes using redis.asyncio for non-blocking fan-out.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from app.core.cache import get_redis  # imported at module level for test patchability

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "heliox:events:"
HISTORY_PREFIX = "heliox:events:history:"
READ_PREFIX = "heliox:events:read:"
CONN_LEASE_PREFIX = "heliox:events:conn_leases:"
HISTORY_TTL_SECONDS = 7 * 24 * 3600  # 7 days
MAX_HISTORY = 100
MAX_CONNS_PER_TEAM = 5
CONN_LEASE_SECONDS = 75  # > 2 x the 30 s SSE ping that renews it


class EventType(str, Enum):
    ANOMALY_DETECTED = "anomaly.detected"
    BUDGET_WARNING = "budget.warning"
    BUDGET_BREACH = "budget.breach"
    SYNC_COMPLETED = "sync.completed"
    SYNC_FAILED = "sync.failed"
    COST_SPIKE = "cost.spike"
    INFERENCE_ALERT = "inference.alert"
    PING = "ping"


@dataclass
class HelioxEvent:
    event_type: EventType
    team_id: str
    payload: dict
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex[:16]}")
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(
            {
                "event_id": self.event_id,
                "event_type": self.event_type.value,
                "team_id": self.team_id,
                "payload": self.payload,
                "timestamp": self.timestamp,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "HelioxEvent":
        d = json.loads(raw)
        return cls(
            event_type=EventType(d["event_type"]),
            team_id=d["team_id"],
            payload=d["payload"],
            event_id=d["event_id"],
            timestamp=d["timestamp"],
        )


def get_channel(team_id: str) -> str:
    return f"{CHANNEL_PREFIX}{team_id}"


# ── Synchronous publish (for Celery tasks and sync service code) ──────────────


def publish_event_sync(team_id: str, event: HelioxEvent) -> None:
    """Publish event to Redis channel + append to history sorted set.

    Fire-and-forget: logs on failure but never raises.
    """
    r = get_redis()
    if r is None:
        logger.warning("events: Redis unavailable — event %s not published", event.event_id)
        return

    payload = event.to_json()
    channel = get_channel(team_id)
    score = time.time()

    try:
        pipe = r.pipeline(transaction=False)
        pipe.publish(channel, payload)
        pipe.zadd(f"{HISTORY_PREFIX}{team_id}", {payload: score})
        pipe.zremrangebyrank(f"{HISTORY_PREFIX}{team_id}", 0, -(MAX_HISTORY + 1))
        pipe.expire(f"{HISTORY_PREFIX}{team_id}", HISTORY_TTL_SECONDS)
        pipe.execute()
        logger.debug("events: published %s to team=%s", event.event_type.value, team_id)
    except Exception as exc:
        logger.warning(
            "events: publish failed for team=%s event=%s — %s",
            team_id,
            event.event_id,
            exc,
        )


# ── Async publish (for FastAPI route handlers) ────────────────────────────────


async def publish_event(team_id: str, event: HelioxEvent) -> None:
    """Async fire-and-forget publish. Never raises."""
    import asyncio

    try:
        await asyncio.get_event_loop().run_in_executor(None, publish_event_sync, team_id, event)
    except Exception as exc:
        logger.warning("events: async publish failed — %s", exc)


# ── Connection slot leases ────────────────────────────────────────────────────

# Drop expired leases, then renew this connection's lease or admit it if a slot
# is free. Returns 1 if the connection holds a slot, 0 if the team is full.
_ACQUIRE_SLOT_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local lease = tonumber(ARGV[2])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if not redis.call('ZSCORE', KEYS[1], ARGV[3]) and redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[1]) then
  return 0
end
redis.call('ZADD', KEYS[1], now + lease, ARGV[3])
redis.call('EXPIRE', KEYS[1], math.ceil(lease) + 1)
return 1
"""


def _lease_key(team_id: str) -> str:
    return f"{CONN_LEASE_PREFIX}{team_id}"


def acquire_conn_slot(team_id: str, conn_id: str) -> bool | None:
    """Take (or renew) a connection slot. True = held, False = team full, None = Redis unavailable."""
    r = get_redis()
    if r is None:
        return None
    try:
        held = r.eval(_ACQUIRE_SLOT_LUA, 1, _lease_key(team_id), MAX_CONNS_PER_TEAM, CONN_LEASE_SECONDS, conn_id)
        return int(held) == 1
    except Exception as exc:
        logger.warning("events: acquire_conn_slot failed for team=%s — %s", team_id, exc)
        return None


def release_conn_slot(team_id: str, conn_id: str) -> None:
    """Give a slot back. Never raises; an unreleased slot expires with its lease."""
    r = get_redis()
    if r is None:
        return
    try:
        r.zrem(_lease_key(team_id), conn_id)
    except Exception as exc:
        logger.warning("events: release_conn_slot failed for team=%s — %s", team_id, exc)


def get_conn_count(team_id: str) -> int:
    """Live (unexpired) connection slots for the team."""
    r = get_redis()
    if r is None:
        return 0
    try:
        seconds, micros = r.time()
        return int(r.zcount(_lease_key(team_id), seconds + micros / 1_000_000, "+inf"))
    except Exception:
        return 0


# ── History + read-state helpers ──────────────────────────────────────────────


def get_recent_events(team_id: str, limit: int = 50) -> list[dict]:
    """Return last `limit` events from history sorted set, newest first."""
    r = get_redis()
    if r is None:
        return []
    try:
        raws = r.zrevrange(f"{HISTORY_PREFIX}{team_id}", 0, limit - 1)
        read_ids: set[str] = set(r.smembers(f"{READ_PREFIX}{team_id}") or [])
        result = []
        for raw in raws:
            try:
                d = json.loads(raw)
                d["read"] = d.get("event_id", "") in read_ids
                result.append(d)
            except Exception:
                continue
        return result
    except Exception as exc:
        logger.warning("events: get_recent_events failed — %s", exc)
        return []


def mark_event_read(team_id: str, event_id: str) -> bool:
    """Mark an event as read. Returns True on success."""
    r = get_redis()
    if r is None:
        return False
    try:
        read_key = f"{READ_PREFIX}{team_id}"
        r.sadd(read_key, event_id)
        r.expire(read_key, HISTORY_TTL_SECONDS)
        return True
    except Exception as exc:
        logger.warning("events: mark_event_read failed — %s", exc)
        return False
