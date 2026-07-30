"""Server-Sent Events endpoint for real-time push notifications.

GET  /api/v1/events/stream        — long-lived SSE stream (auth via X-API-Key or JWT cookie)
GET  /api/v1/events/recent        — last 50 events for the team
POST /api/v1/events/{id}/read     — mark an event as read

SSE architecture:
  ┌──────────────────────────────────────────────────────────────┐
  │  Celery / service layer                                       │
  │    publish_event_sync(team_id, event)                        │
  │       │                                                       │
  │       └─► Redis PUBLISH  heliox:events:{team_id}             │
  │                │                                              │
  │                ▼                                              │
  │  SSE endpoint (one per connected browser tab)                │
  │    asyncio.Queue ◄─── redis.asyncio subscriber task          │
  │          │                                                    │
  │          └─► StreamingResponse generator ─► browser          │
  └──────────────────────────────────────────────────────────────┘

Connection lifecycle:
  1. Client connects → check conn limit → INCR counter in Redis
  2. Spawn background task to subscribe to Redis channel
  3. Yield events from queue + periodic pings (every 30 s)
  4. Client disconnects → cancel background task → DECR counter
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.events import (
    MAX_CONNS_PER_TEAM,
    decrement_conn,
    get_channel,
    get_conn_count,
    get_recent_events,
    increment_conn,
    mark_event_read,
)
from app.core.tenant import get_effective_team_id

logger = logging.getLogger(__name__)
router = APIRouter()

PING_INTERVAL_SECONDS = 30


# ── Auth: accepts X-API-Key header OR JWT session cookie ─────────────────────


async def _resolve_team_id(
    request: Request,
    db: Session = Depends(get_db),
) -> UUID:
    """Resolve team_id from API key header or JWT session cookie.

    EventSource in browsers cannot set custom headers, so the SSE endpoint
    must also accept the existing JWT cookie session.
    """
    # 1. Try X-API-Key header (CLI / programmatic access)
    x_api_key = request.headers.get("X-API-Key")
    if x_api_key:
        from app.core.security import get_team_api_key_if_present

        api_key = get_team_api_key_if_present(x_api_key=x_api_key, db=db)
        if api_key:
            return get_effective_team_id(api_key)

    # 2. Try JWT session cookie (browser EventSource)
    from app.auth.cookie_auth import (
        get_token_from_cookie_or_header,
        is_token_blacklisted,
    )
    from app.auth.security import SECRET_KEY
    from app.crud import user as crud_user
    import jwt
    from jwt import PyJWTError as JWTError

    token = get_token_from_cookie_or_header(request)
    if token and not is_token_blacklisted(token):
        try:
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=["HS256"],
                options={"require": ["exp", "sub"]},
            )
            email = payload.get("sub")
            if email:
                user = crud_user.get_by_email(db, email=email)
                if user:
                    # Resolve team from TeamMember (first active team)
                    from app.models.team_member import TeamMember

                    member = db.query(TeamMember).filter(TeamMember.user_id == user.id).first()
                    if member:
                        return member.team_id
        except (JWTError, Exception):
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide X-API-Key header or a valid session.",
    )


# ── SSE stream helpers ────────────────────────────────────────────────────────


def _sse_line(event_type: str, data: str, event_id: str) -> str:
    """Format a single SSE message."""
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


def _ping_line() -> str:
    return f"id: ping-{int(time.time())}\nevent: ping\ndata: {{}}\n\n"


async def _redis_subscriber(
    channel: str,
    queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> None:
    """Subscribe to a Redis channel and push messages into the queue.

    Runs as a background asyncio task for the duration of the SSE connection.
    Uses redis.asyncio (bundled with redis-py 4.2+).
    """
    from app.core.config import get_settings
    import redis.asyncio as aioredis

    settings = get_settings()
    r: Optional[aioredis.Redis] = None
    pubsub = None

    try:
        r = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            ssl_cert_reqs=None,
        )
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        logger.debug("SSE: subscribed to %s", channel)

        while not stop_event.is_set():
            try:
                message = await asyncio.wait_for(pubsub.get_message(ignore_subscribe_messages=True), timeout=1.0)
                if message and message.get("type") == "message":
                    await queue.put(message["data"])
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("SSE: redis subscriber error — %s", exc)
                # Put an error sentinel so the generator can close cleanly
                await queue.put(None)
                break

    except Exception as exc:
        logger.warning("SSE: redis connection failed — %s", exc)
        await queue.put(None)
    finally:
        try:
            if pubsub:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            if r:
                await r.aclose()
        except Exception:
            pass
        logger.debug("SSE: unsubscribed from %s", channel)


async def _sse_generator(
    team_id: UUID,
    queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted strings. Sends pings every 30 s to prevent proxy timeouts."""
    last_ping = time.monotonic()
    try:
        while True:
            now = time.monotonic()

            # Periodic ping
            if now - last_ping >= PING_INTERVAL_SECONDS:
                yield _ping_line()
                last_ping = now

            # Try to read an event (short timeout keeps pings timely)
            try:
                raw = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if raw is None:
                # Redis subscriber signalled an error — close stream gracefully
                yield _sse_line(
                    "error",
                    json.dumps({"message": "Stream interrupted. Please reconnect."}),
                    f"err-{int(time.time())}",
                )
                break

            try:
                event_data = json.loads(raw)
                yield _sse_line(
                    event_data.get("event_type", "message"),
                    raw,
                    event_data.get("event_id", f"evt-{int(time.time())}"),
                )
            except Exception as exc:
                logger.warning("SSE: bad event payload — %s", exc)

    except asyncio.CancelledError:
        pass
    finally:
        stop_event.set()


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/stream",
    summary="Real-time SSE event stream",
    description=(
        "Long-lived Server-Sent Events stream. "
        "Authenticate via X-API-Key header or JWT session cookie. "
        "Max 5 concurrent connections per team. "
        "Sends a `ping` event every 30 seconds to prevent proxy timeouts.\n\n"
        "Test with:\n"
        "`curl -N -H 'X-API-Key: hx_...' http://localhost:8000/api/v1/events/stream`"
    ),
)
async def event_stream(
    request: Request,
    team_id: UUID = Depends(_resolve_team_id),
) -> StreamingResponse:
    team_id_str = str(team_id)

    # Enforce per-team connection limit
    conn_count = get_conn_count(team_id_str)
    if conn_count >= MAX_CONNS_PER_TEAM:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Maximum {MAX_CONNS_PER_TEAM} concurrent SSE connections per team. "
                "Close an existing connection before opening a new one."
            ),
        )

    channel = get_channel(team_id_str)
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    stop_event = asyncio.Event()

    # Increment connection counter
    increment_conn(team_id_str)

    # Start Redis subscriber task
    subscriber_task = asyncio.create_task(_redis_subscriber(channel, queue, stop_event))

    async def _cleanup() -> None:
        stop_event.set()
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            pass
        decrement_conn(team_id_str)
        logger.debug("SSE: connection closed for team=%s", team_id_str)

    async def _stream() -> AsyncGenerator[str, None]:
        try:
            async for chunk in _sse_generator(team_id, queue, stop_event):
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                yield chunk
        finally:
            await _cleanup()

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get(
    "/recent",
    summary="Recent events for the team (last 50)",
)
async def recent_events(
    limit: int = Query(default=50, ge=1, le=100, description="Number of events to return"),
    team_id: UUID = Depends(_resolve_team_id),
) -> Any:
    team_id_str = str(team_id)
    events = get_recent_events(team_id_str, limit=limit)
    unread_count = sum(1 for e in events if not e.get("read", False))
    return {
        "events": events,
        "unread_count": unread_count,
    }


@router.post(
    "/{event_id}/read",
    status_code=status.HTTP_200_OK,
    summary="Mark an event as read",
)
async def read_event(
    event_id: str,
    team_id: UUID = Depends(_resolve_team_id),
) -> Any:
    team_id_str = str(team_id)
    ok = mark_event_read(team_id_str, event_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not mark event as read. Redis may be unavailable.",
        )
    return {"ok": True, "event_id": event_id}
