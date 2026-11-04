"""Durable staging: fenced, idempotent per page, and read back only for a complete stream."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.integrations.ledger.base import SourcePage
from app.services.cost_ledger import LEASE_TTL, LEASED_PHASES, CostLine, LedgerFenced


def affected_rows(result: Any) -> int:
    """How many rows a guarded update changed. Every fenced write checks this."""
    return result.rowcount


class StagingConflict(Exception):
    """A page delivered a different value for a line already staged in this attempt."""


def heartbeat(session: Session, run_id: UUID, attempt: int, token: int) -> None:
    """Extend a live lease, or refuse. An expired lease is never revived: a newer attempt may own the run."""
    updated = affected_rows(
        session.execute(
            text(
                "UPDATE cost_sync_leases l SET expires_at = clock_timestamp() + :ttl, heartbeat_at = clock_timestamp() "
                "FROM integration_sync_runs r WHERE r.id = :r AND l.connection_id = r.connection_id "
                "AND r.attempt = :a AND r.lease_token = :t AND r.phase = ANY(:leased) "
                "AND l.holder_run_id = :r AND l.holder_attempt = :a AND l.token = :t "
                "AND l.expires_at > clock_timestamp()"
            ),
            {"r": run_id, "a": attempt, "t": token, "ttl": LEASE_TTL, "leased": list(LEASED_PHASES)},
        )
    )
    if updated != 1:
        raise LedgerFenced("this attempt no longer holds a live lease")
    session.execute(
        text("UPDATE integration_sync_runs SET heartbeat_at = clock_timestamp() WHERE id = :r"), {"r": run_id}
    )


def stage_page(session: Session, run_id: UUID, attempt: int, stream_id: UUID, page: SourcePage) -> None:
    """Stage one page under run, attempt and stream. A re-delivered page changes nothing; a different value refuses."""
    for line in page.lines:
        inserted = session.execute(
            text(
                "INSERT INTO cost_sync_staging (sync_run_id, attempt, stream_id, usage_date, dim_1, dim_2, line_kind, "
                "line_key, currency, canonical_service, charge_class, page_seq, amount, amount_usd, fx_rate, fx_source, "
                "cost_bucket, is_estimated, payload_sha256) VALUES (:r, :a, :s, :d, :d1, :d2, :lk, :key, :cur, :svc, "
                ":cls, :seq, :amt, :usd, :fx, :fxs, :bucket, :est, :sha) "
                "ON CONFLICT ON CONSTRAINT cost_sync_staging_pkey DO NOTHING RETURNING 1"
            ),
            {
                "r": run_id,
                "a": attempt,
                "s": stream_id,
                "d": line.usage_date,
                "d1": line.dim_1,
                "d2": line.dim_2,
                "lk": line.line_kind,
                "key": line.line_key,
                "cur": line.currency,
                "svc": line.canonical_service,
                "cls": line.charge_class,
                "seq": page.seq,
                "amt": line.amount,
                "usd": line.amount_usd,
                "fx": line.fx_rate,
                "fxs": line.fx_source,
                "bucket": line.cost_bucket,
                "est": line.is_estimated,
                "sha": line.payload_sha256,
            },
        ).scalar()
        if inserted is None:
            existing = session.execute(
                text(
                    "SELECT payload_sha256 FROM cost_sync_staging WHERE sync_run_id = :r AND attempt = :a "
                    "AND stream_id = :s AND usage_date = :d AND dim_1 = :d1 AND dim_2 = :d2 AND line_kind = :lk "
                    "AND line_key = :key AND currency = :cur"
                ),
                {
                    "r": run_id,
                    "a": attempt,
                    "s": stream_id,
                    "d": line.usage_date,
                    "d1": line.dim_1,
                    "d2": line.dim_2,
                    "lk": line.line_kind,
                    "key": line.line_key,
                    "cur": line.currency,
                },
            ).scalar_one()
            if bytes(existing) != line.payload_sha256:
                raise StagingConflict("conflicting value for a staged line")
    updated = affected_rows(
        session.execute(
            text(
                "UPDATE cost_sync_run_streams rs SET status = :st, pages = GREATEST(pages, :n), updated_at = now(), "
                "staged_rows = (SELECT count(*) FROM cost_sync_staging x WHERE x.sync_run_id = rs.sync_run_id "
                "AND x.attempt = rs.attempt AND x.stream_id = rs.stream_id), "
                "staged_total_usd = (SELECT coalesce(sum(amount_usd), 0) FROM cost_sync_staging x "
                "WHERE x.sync_run_id = rs.sync_run_id AND x.attempt = rs.attempt AND x.stream_id = rs.stream_id) "
                "WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s AND status IN ('pending', 'fetching')"
            ),
            {
                "r": run_id,
                "a": attempt,
                "s": stream_id,
                "st": "complete" if page.is_last else "fetching",
                "n": page.seq + 1,
            },
        )
    )
    if updated != 1:
        raise LedgerFenced("the stream is not being fetched by this attempt")


def staged_lines(session: Session, run_id: UUID, attempt: int, stream_id: UUID) -> list[CostLine]:
    """Read one stream back through CostLine, so staged data passes the same validation as fresh data."""
    rows = session.execute(
        text(
            "SELECT usage_date, line_kind, canonical_service, charge_class, cost_bucket, currency, amount, amount_usd, "
            "dim_1, dim_2, line_key, fx_rate, fx_source, is_estimated FROM cost_sync_staging "
            "WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s ORDER BY usage_date, dim_1, dim_2, line_kind, line_key"
        ),
        {"r": run_id, "a": attempt, "s": stream_id},
    )
    return [
        CostLine(
            r.usage_date,
            r.line_kind,
            r.canonical_service,
            r.charge_class,
            r.cost_bucket,
            r.currency,
            r.amount,
            r.amount_usd,
            r.dim_1,
            r.dim_2,
            r.line_key,
            r.fx_rate,
            r.fx_source,
            r.is_estimated,
        )
        for r in rows
    ]


def clear_staging(session: Session, run_id: UUID) -> None:
    """Staging lives until the run is terminal, for every attempt; the model documents it as temporary."""
    session.execute(text("DELETE FROM cost_sync_staging WHERE sync_run_id = :r"), {"r": run_id})


def advance_checkpoint(
    session: Session,
    team_id: UUID,
    stream_id: UUID,
    days: Iterable[date],
    fetch_started_at: datetime,
    watermark: Optional[datetime],
) -> None:
    """Advance only over a contiguous run of accepted final days, and never backwards. Same transaction as publish."""
    ordered = sorted(days)
    if not ordered:
        return
    states = dict(
        session.execute(
            text("SELECT usage_date, state FROM cost_source_stream_days WHERE stream_id = :s AND usage_date = ANY(:d)"),
            {"s": stream_id, "d": ordered},
        )
        .tuples()
        .all()
    )
    final_through = None
    for day in ordered:
        if states.get(day) != "final":
            break
        final_through = day
    current = session.execute(
        text("SELECT final_through FROM cost_source_stream_checkpoints WHERE stream_id = :s"), {"s": stream_id}
    ).scalar()
    if final_through is not None and current is not None and (ordered[0] - current).days > 1:
        final_through = None  # a gap before this window: nothing proves the days in between
    session.execute(
        text(
            "INSERT INTO cost_source_stream_checkpoints AS c (team_id, stream_id, final_through, export_watermark, "
            "last_complete_fetch_at) VALUES (:t, :s, :ft, :w, :f) ON CONFLICT (stream_id) DO UPDATE SET "
            "final_through = GREATEST(c.final_through, EXCLUDED.final_through), "
            "export_watermark = GREATEST(c.export_watermark, EXCLUDED.export_watermark), "
            "last_complete_fetch_at = GREATEST(c.last_complete_fetch_at, EXCLUDED.last_complete_fetch_at)"
        ),
        {"t": team_id, "s": stream_id, "ft": final_through, "w": watermark, "f": fetch_started_at},
    )
