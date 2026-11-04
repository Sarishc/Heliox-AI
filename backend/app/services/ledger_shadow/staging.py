"""Durable staging: fenced, idempotent per page, and read back only for a complete stream."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
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


class MissingPage(Exception):
    """A page arrived ahead of one that was never staged. A final-page marker cannot paper over the gap."""


def heartbeat(session: Session, run_id: UUID, attempt: int, token: int) -> None:
    """Extend a live lease, or refuse. An expired lease is never revived: a newer attempt may own the run."""
    # Run row first, then lease: the order every path uses. Taking them the other way round deadlocks the reaper.
    session.execute(text("SELECT 1 FROM integration_sync_runs WHERE id = :r FOR UPDATE"), {"r": run_id})
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
    """Stage one page under run, attempt and stream.

    Pages must arrive contiguously from zero. A re-delivered page must match what is staged and changes
    nothing; a skipped page, or a different value for a staged line, refuses.
    """
    progress = session.execute(
        text(
            "SELECT status, pages FROM cost_sync_run_streams WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s "
            "FOR UPDATE"
        ),
        {"r": run_id, "a": attempt, "s": stream_id},
    ).one_or_none()
    if progress is None or progress.status not in ("pending", "fetching"):
        raise LedgerFenced("the stream is not being fetched by this attempt")
    if page.seq < 0 or page.seq > progress.pages:
        raise MissingPage(f"page {page.seq} arrived after {progress.pages} contiguous pages")
    replay = page.seq < progress.pages
    if replay and page.is_last and page.seq != progress.pages - 1:
        raise StagingConflict("an earlier page claims to be the last")
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
        if inserted is not None and replay:
            raise StagingConflict("a re-delivered page holds a line it did not have before")
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
    if replay:
        delivered = {line.payload_sha256 for line in page.lines}
        kept = session.execute(
            text(
                "SELECT payload_sha256 FROM cost_sync_staging WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s "
                "AND page_seq = :seq"
            ),
            {"r": run_id, "a": attempt, "s": stream_id, "seq": page.seq},
        )
        if any(bytes(row.payload_sha256) not in delivered for row in kept):
            raise StagingConflict("a re-delivered page is missing a line it had before")
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


def record_complete_fetch(
    session: Session,
    team_id: UUID,
    stream_id: UUID,
    fetch_started_at: datetime,
    watermark: Optional[datetime],
) -> None:
    """Record, in the publish transaction, that a complete fetch was accepted. Both values only move forward.

    ``final_through`` stays NULL. Migration 038 stores no starting boundary, so a value there would read as
    "every earlier day is final" even for a stream whose first window was yesterday. Use ``stream_coverage``,
    which takes an explicit start and reports every day in the range.
    """
    session.execute(
        text(
            "INSERT INTO cost_source_stream_checkpoints AS c (team_id, stream_id, export_watermark, "
            "last_complete_fetch_at) VALUES (:t, :s, :w, :f) ON CONFLICT (stream_id) DO UPDATE SET "
            "export_watermark = GREATEST(c.export_watermark, EXCLUDED.export_watermark), "
            "last_complete_fetch_at = GREATEST(c.last_complete_fetch_at, EXCLUDED.last_complete_fetch_at)"
        ),
        {"t": team_id, "s": stream_id, "w": watermark, "f": fetch_started_at},
    )
