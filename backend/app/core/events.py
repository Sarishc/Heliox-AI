"""Redis-backed event bus for real-time SSE fan-out.

Channel pattern:  heliox:events:{team_id}          — live pub/sub
History key:      heliox:events:history:{team_id}  — sorted set, last 100 events
Read set:         heliox:events:read:{team_id}     — set of read event_ids
Connection count: heliox:events:conns:{team_id}    — integer counter (TTL 60 s)

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
from typing import Optional
from uuid import UUID, uuid4

from app.core.cache import get_redis  # imported at module level for test patchability

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "heliox:events:"
HISTORY_PREFIX = "heliox:events:history:"
READ_PREFIX = "heliox:events:read:"
CONN_PREFIX = "heliox:events:conns:"
HISTORY_TTL_SECONDS = 7 * 24 * 3600  # 7 days
MAX_HISTORY = 100
MAX_CONNS_PER_TEAM = 5


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
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

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
            team_id, event.event_id, exc,
        )


# ── Async publish (for FastAPI route handlers) ────────────────────────────────

async def publish_event(team_id: str, event: HelioxEvent) -> None:
    """Async fire-and-forget publish. Never raises."""
    import asyncio

    try:
        await asyncio.get_event_loop().run_in_executor(
            None, publish_event_sync, team_id, event
        )
    except Exception as exc:
        logger.warning("events: async publish failed — %s", exc)


# ── Connection counter helpers ────────────────────────────────────────────────

def increment_conn(team_id: str) -> int:
    """Increment SSE connection count for team. Returns new count."""
    r = get_redis()
    if r is None:
        return 0
    key = f"{CONN_PREFIX}{team_id}"
    try:
        count = r.incr(key)
        r.expire(key, 60)  # TTL acts as a safety valve if decr is missed
        return int(count)
    except Exception:
        return 0


def decrement_conn(team_id: str) -> None:
    """Decrement SSE connection count for team."""
    r = get_redis()
    if r is None:
        return
    key = f"{CONN_PREFIX}{team_id}"
    try:
        count = r.decr(key)
        if count <= 0:
            r.delete(key)
    except Exception:
        pass


def get_conn_count(team_id: str) -> int:
    r = get_redis()
    if r is None:
        return 0
    try:
        val = r.get(f"{CONN_PREFIX}{team_id}")
        return int(val) if val else 0
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
        read_ids: set[str] = set(
            r.smembers(f"{READ_PREFIX}{team_id}") or []
        )
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
