"""Reaper for abandoned shadow runs. Database state decides; nothing depends on a worker's memory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Mapping, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.cost_ledger import INFLIGHT_PHASES, LEASE_TTL
from app.services.ledger_shadow.staging import affected_rows, clear_staging


@dataclass(frozen=True)
class ReapAction:
    run_id: UUID
    action: str  # requeue | abandoned | dispatch_expired
    reason: str


def append_recovery_event(session: Session, run_id: UUID, event: Mapping[str, Any]) -> None:
    """The auditable trail of what happened to a run across attempts. The caller holds the run row lock."""
    current = session.execute(
        text("SELECT metrics_json FROM integration_sync_runs WHERE id = :r"), {"r": run_id}
    ).scalar()
    metrics = dict(current or {})
    ledger = dict(metrics.get("ledger") or {})
    ledger["recovery"] = [*ledger.get("recovery", []), {**event, "at": _now(session)}]
    metrics["ledger"] = ledger
    session.execute(
        text("UPDATE integration_sync_runs SET metrics_json = CAST(:m AS json) WHERE id = :r"),
        {"m": json.dumps(metrics), "r": run_id},
    )


def terminate_run(
    session: Session, run_id: UUID, *, attempt: int, token: Optional[int], phase: str, reason: str
) -> bool:
    """End a run that has no live worker, conditionally: only if it is still this attempt and still in flight."""
    updated = affected_rows(
        session.execute(
            text(
                "UPDATE integration_sync_runs SET phase = :p, status = 'failed', finished_at = now(), "
                "phase_changed_at = clock_timestamp(), error_details = CAST(:d AS json) WHERE id = :r AND attempt = :a "
                "AND lease_token IS NOT DISTINCT FROM :t AND phase = ANY(:inflight)"
            ),
            {
                "p": phase,
                "d": json.dumps({"reason": reason, "attempt": attempt}),
                "r": run_id,
                "a": attempt,
                "t": token,
                "inflight": list(INFLIGHT_PHASES),
            },
        )
    )
    if updated != 1:
        return False
    _fence_open_streams(session, run_id, attempt)
    session.execute(
        text(
            "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
            "WHERE holder_run_id = :r AND token IS NOT DISTINCT FROM :t"
        ),
        {"r": run_id, "t": token},
    )
    clear_staging(session, run_id)
    append_recovery_event(
        session, run_id, {"event": "terminated", "phase": phase, "reason": reason, "attempt": attempt}
    )
    return True


def reap_abandoned_runs(session: Session, *, limit: int = 100, grace: timedelta = LEASE_TTL) -> list[ReapAction]:
    """Find in-flight runs with no live worker and decide what happens. The caller commits, then dispatches requeues.

    A live lease is always left alone. An expired lease is not proof that the provider fetch failed, so
    it only makes the run eligible for a new attempt; nothing is marked failed until attempts run out.
    A worker holding a lock on the run is skipped, not waited for.
    """
    actions: list[ReapAction] = []
    runs = session.execute(
        text(
            "SELECT id, connection_id, phase, attempt, max_attempts, lease_token, dispatch_deadline_at < clock_timestamp() "
            "AS dispatch_expired, heartbeat_at < clock_timestamp() - :grace AS quiet FROM integration_sync_runs "
            "WHERE pipeline = 'ledger' AND phase = ANY(:inflight) ORDER BY started_at LIMIT :limit "
            "FOR UPDATE SKIP LOCKED"
        ),
        {"inflight": list(INFLIGHT_PHASES), "limit": limit, "grace": grace},
    ).all()
    for run in runs:
        if run.phase == "queued":
            if run.dispatch_expired and run.attempt == 0:
                if terminate_run(
                    session, run.id, attempt=0, token=None, phase="dispatch_expired", reason="never_dispatched"
                ):
                    actions.append(ReapAction(run.id, "dispatch_expired", "never_dispatched"))
            continue
        lease = session.execute(
            text(
                "SELECT holder_run_id, holder_attempt, token, expires_at > clock_timestamp() AS live "
                "FROM cost_sync_leases WHERE connection_id = :c FOR UPDATE"
            ),
            {"c": run.connection_id},
        ).one_or_none()
        holds = lease is not None and lease.holder_run_id == run.id
        if lease is not None and holds and lease.live:
            continue  # an active worker
        if not holds and not run.quiet:
            continue  # released for a retry that is on its way
        if run.attempt >= run.max_attempts:
            if terminate_run(
                session,
                run.id,
                attempt=run.attempt,
                token=run.lease_token,
                phase="abandoned",
                reason="attempts_exhausted",
            ):
                actions.append(ReapAction(run.id, "abandoned", "attempts_exhausted"))
            continue
        _fence_open_streams(session, run.id, run.attempt)
        if holds:
            released = affected_rows(
                session.execute(
                    text(
                        "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
                        "WHERE connection_id = :c AND holder_run_id = :r AND holder_attempt = :a AND token = :t "
                        "AND expires_at <= clock_timestamp()"
                    ),
                    {"c": run.connection_id, "r": run.id, "a": run.attempt, "t": run.lease_token},
                )
            )
            if released != 1:
                continue
        append_recovery_event(
            session, run.id, {"event": "lease_expired_requeued", "attempt": run.attempt, "token": run.lease_token}
        )
        actions.append(ReapAction(run.id, "requeue", "lease_expired"))
    return actions


def _fence_open_streams(session: Session, run_id: UUID, attempt: int) -> None:
    session.execute(
        text(
            "UPDATE cost_sync_run_streams SET status = 'fenced', error_code = COALESCE(error_code, 'attempt_abandoned'), "
            "updated_at = now() WHERE sync_run_id = :r AND attempt = :a AND status IN ('pending', 'fetching', 'complete')"
        ),
        {"r": run_id, "a": attempt},
    )


def _now(session: Session) -> str:
    return session.execute(text("SELECT clock_timestamp()")).scalar_one().isoformat()
