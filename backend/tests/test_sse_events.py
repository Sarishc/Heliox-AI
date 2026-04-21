"""Tests for the SSE event bus (publish, history, read-state, tenant isolation)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_event(team_id: str, event_type: str = "anomaly.detected"):
    from app.core.events import EventType, HelioxEvent

    return HelioxEvent(
        event_type=EventType(event_type),
        team_id=team_id,
        payload={"message": "test anomaly", "severity": "medium"},
    )


def _mock_redis_pipe():
    """Return a (mock_redis, mock_pipe) pair with a working pipeline()."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute.return_value = [1, 1, 0, True]
    mock_redis.pipeline.return_value = mock_pipe
    return mock_redis, mock_pipe


# ── 1: publish_event_sync writes to the correct Redis channel ────────────────


def test_publish_event_sync_calls_correct_channel():
    """publish_event_sync PUBLISH-es to heliox:events:{team_id}."""
    from app.core.events import publish_event_sync, get_channel

    team_id = str(uuid4())
    event = _make_event(team_id)
    mock_redis, mock_pipe = _mock_redis_pipe()

    with patch("app.core.events.get_redis", return_value=mock_redis):
        publish_event_sync(team_id, event)

    mock_pipe.publish.assert_called_once_with(get_channel(team_id), event.to_json())


# ── 2: publish_event_sync writes to history sorted set ───────────────────────


def test_publish_event_sync_writes_history():
    """publish_event_sync ZADDs to heliox:events:history:{team_id}."""
    from app.core.events import publish_event_sync, HISTORY_PREFIX

    team_id = str(uuid4())
    event = _make_event(team_id)
    mock_redis, mock_pipe = _mock_redis_pipe()

    with patch("app.core.events.get_redis", return_value=mock_redis):
        publish_event_sync(team_id, event)

    history_key = f"{HISTORY_PREFIX}{team_id}"
    zadd_calls = mock_pipe.zadd.call_args_list
    assert len(zadd_calls) == 1
    assert zadd_calls[0].args[0] == history_key


# ── 3: SSE endpoint returns text/event-stream content-type ───────────────────


def test_event_stream_content_type(db_session):
    """GET /events/stream must set content-type: text/event-stream."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.team import Team
    from app.models.team_api_key import TeamAPIKey
    from app.core.db import get_db

    team = Team(name="SSE CT Team")
    db_session.add(team)
    db_session.flush()

    raw_key = "hx_ssect_" + uuid4().hex
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="sse-ct",
            key_hash=TeamAPIKey.hash_key(raw_key),
            is_active=True,
        )
    )
    db_session.flush()

    app.dependency_overrides[get_db] = lambda: db_session

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None  # conn count = 0
    mock_redis.incr.return_value = 1
    mock_redis.expire.return_value = True
    mock_redis.decr.return_value = 0

    async def _fake_subscriber(channel, queue, stop_event):
        await queue.put(None)  # close immediately

    with (
        patch("app.core.cache.get_redis", return_value=mock_redis),
        patch("app.core.events.get_redis", return_value=mock_redis),
        patch("app.core.rate_limit.require_redis", return_value=mock_redis),
        patch("app.api.routes.events._redis_subscriber", side_effect=_fake_subscriber),
    ):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/events/stream", headers={"X-API-Key": raw_key})

    assert "text/event-stream" in resp.headers.get("content-type", "")
    app.dependency_overrides.clear()


# ── 4: GET /events/recent returns events in correct shape ────────────────────


def test_events_recent_returns_correct_shape(db_session):
    """GET /events/recent returns {events, unread_count} with correct types."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.team import Team
    from app.models.team_api_key import TeamAPIKey
    from app.core.db import get_db

    team = Team(name="Recent Team")
    db_session.add(team)
    db_session.flush()

    raw_key = "hx_recent_" + uuid4().hex
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="recent",
            key_hash=TeamAPIKey.hash_key(raw_key),
            is_active=True,
        )
    )
    db_session.flush()

    sample = [
        {
            "event_id": f"evt_{i}",
            "event_type": "anomaly.detected",
            "team_id": str(team.id),
            "payload": {},
            "timestamp": "2026-04-20T10:00:00Z",
            "read": False,
        }
        for i in range(3)
    ]

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None

    app.dependency_overrides[get_db] = lambda: db_session

    with (
        patch("app.core.cache.get_redis", return_value=mock_redis),
        patch("app.core.rate_limit.is_rate_limited", return_value=(False, 60)),
        patch("app.api.routes.events.get_recent_events", return_value=sample),
    ):
        client = TestClient(app)
        resp = client.get("/api/v1/events/recent", headers={"X-API-Key": raw_key})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    assert "unread_count" in body
    assert len(body["events"]) == 3
    assert body["unread_count"] == 3
    app.dependency_overrides.clear()


# ── 5: POST /events/{id}/read returns ok:true ────────────────────────────────


def test_mark_event_read_endpoint(db_session):
    """POST /events/{id}/read returns {ok: true, event_id: ...}."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.team import Team
    from app.models.team_api_key import TeamAPIKey
    from app.core.db import get_db

    team = Team(name="Mark Read Team")
    db_session.add(team)
    db_session.flush()

    raw_key = "hx_markread_" + uuid4().hex
    db_session.add(
        TeamAPIKey(
            team_id=team.id,
            key_name="mark-read",
            key_hash=TeamAPIKey.hash_key(raw_key),
            is_active=True,
        )
    )
    db_session.flush()

    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis.get.return_value = None

    app.dependency_overrides[get_db] = lambda: db_session

    with (
        patch("app.core.cache.get_redis", return_value=mock_redis),
        patch("app.core.rate_limit.is_rate_limited", return_value=(False, 60)),
        patch("app.api.routes.events.mark_event_read", return_value=True) as mock_mark,
    ):
        client = TestClient(app)
        resp = client.post(
            "/api/v1/events/evt_abc123/read",
            headers={"X-API-Key": raw_key},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["event_id"] == "evt_abc123"
    mock_mark.assert_called_once_with(str(team.id), "evt_abc123")
    app.dependency_overrides.clear()


# ── 6: tenant isolation — different teams use different channels ──────────────


def test_tenant_isolation_separate_channels():
    """Teams A and B have non-overlapping Redis channels."""
    from app.core.events import get_channel

    team_a = str(uuid4())
    team_b = str(uuid4())

    channel_a = get_channel(team_a)
    channel_b = get_channel(team_b)

    assert channel_a != channel_b
    assert team_a in channel_a
    assert team_b in channel_b
    assert team_a not in channel_b
    assert team_b not in channel_a


# ── 7a: publish_event_sync with Redis=None does not raise ────────────────────


def test_publish_event_sync_redis_unavailable_does_not_raise():
    """publish_event_sync is fire-and-forget — Redis=None must never raise."""
    from app.core.events import publish_event_sync

    team_id = str(uuid4())
    event = _make_event(team_id)

    with patch("app.core.events.get_redis", return_value=None):
        publish_event_sync(team_id, event)  # must not raise


# ── 7b: publish_event_sync pipeline error does not raise ─────────────────────


def test_publish_event_sync_pipeline_error_does_not_raise():
    """publish_event_sync must swallow even when pipeline.execute() throws."""
    from app.core.events import publish_event_sync

    team_id = str(uuid4())
    event = _make_event(team_id)

    mock_redis, mock_pipe = _mock_redis_pipe()
    mock_pipe.execute.side_effect = ConnectionError("Redis gone")

    with patch("app.core.events.get_redis", return_value=mock_redis):
        publish_event_sync(team_id, event)  # must not raise


# ── 8: anomaly detection triggers SSE publish ────────────────────────────────


def test_anomaly_detection_triggers_sse_publish(db_session):
    """check_and_send_anomaly_alert calls publish_event_sync for each anomaly."""
    from app.core.events import EventType
    from app.models.team import Team
    import asyncio

    team = Team(name="Anomaly SSE Team")
    db_session.add(team)
    db_session.flush()

    fake_anomalies = [{"type": "spend_spike", "message": "Spend spiked", "severity": "high"}]

    with (
        patch(
            "app.services.slack_notifications._get_team_slack_config",
            return_value=(None, None, False),
        ),
        patch(
            "app.services.slack_notifications._get_team_email_config",
            return_value=(["test@example.com"], True),
        ),
        patch(
            "app.services.email_notifications.send_anomaly_alert_email",
            return_value=True,
        ),
        patch("app.services.anomaly.AnomalyDetectionService.detect") as mock_detect,
        patch(
            # publish_event_sync is imported inside the function body, so patch the definition
            "app.core.events.publish_event_sync"
        ) as mock_publish,
    ):
        from app.services.anomaly import AnomalyResult
        from app.services.slack_notifications import check_and_send_anomaly_alert

        mock_detect.return_value = AnomalyResult(
            anomalies=fake_anomalies,
            breach_probability=0.0,
            projected_monthly_spend=1000.0,
            budget_usd_monthly=None,
        )

        asyncio.run(check_and_send_anomaly_alert(db_session, team.id))

    assert mock_publish.call_count >= 1
    published_event = mock_publish.call_args[0][1]
    assert published_event.event_type == EventType.ANOMALY_DETECTED
    assert published_event.team_id == str(team.id)


# ── 9: HelioxEvent JSON round-trip ────────────────────────────────────────────


def test_heliox_event_json_round_trip():
    """HelioxEvent.to_json() / from_json() preserves all fields exactly."""
    from app.core.events import EventType, HelioxEvent

    original = HelioxEvent(
        event_type=EventType.BUDGET_BREACH,
        team_id="team-123",
        payload={"budget_usd": 10000, "mtd_spend_usd": 10500},
        event_id="evt_custom",
        timestamp="2026-04-20T12:00:00+00:00",
    )

    restored = HelioxEvent.from_json(original.to_json())

    assert restored.event_type == original.event_type
    assert restored.team_id == original.team_id
    assert restored.payload == original.payload
    assert restored.event_id == original.event_id
    assert restored.timestamp == original.timestamp


# ── 10: get_recent_events marks events as read/unread correctly ───────────────


def test_get_recent_events_marks_read_correctly():
    """get_recent_events cross-references the read set and marks events correctly."""
    from app.core.events import get_recent_events

    team_id = str(uuid4())
    evt_read = "evt_already_read"
    evt_unread = "evt_not_read"

    raw_events = [
        json.dumps(
            {
                "event_id": evt_read,
                "event_type": "anomaly.detected",
                "team_id": team_id,
                "payload": {},
                "timestamp": "2026-04-20T10:00:00Z",
            }
        ),
        json.dumps(
            {
                "event_id": evt_unread,
                "event_type": "budget.warning",
                "team_id": team_id,
                "payload": {},
                "timestamp": "2026-04-20T11:00:00Z",
            }
        ),
    ]

    mock_redis = MagicMock()
    mock_redis.zrevrange.return_value = raw_events
    mock_redis.smembers.return_value = {evt_read}

    with patch("app.core.events.get_redis", return_value=mock_redis):
        events = get_recent_events(team_id, limit=10)

    assert len(events) == 2
    read_map = {e["event_id"]: e["read"] for e in events}
    assert read_map[evt_read] is True
    assert read_map[evt_unread] is False
