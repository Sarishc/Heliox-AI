"""
Runs one shadow sync attempt. No database transaction is open during a provider call.

Transactions:
1. Claim: lock the run, take a newer attempt and a fenced lease, open a progress row per expected stream.
2. One per page: heartbeat (which fences a stale attempt) and stage the page.
3. Publish: for all complete streams, CostLedgerService.publish, checkpoint, clear staging, finish the run.
   Everything in this step commits together or not at all, so a crash leaves the run retryable with
   nothing half-published, and a crash after the commit makes the redelivered task a no-op.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Mapping, Optional, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.integrations.ledger.base import AdapterConfigError, DateWindow, FetchIncomplete, LedgerAdapter, StreamSpec
from app.services.cost_ledger import CostLedgerService, LedgerDisabled, LedgerFenced, Publication, RunNotActive
from app.services.ledger_shadow.activation import (
    ShadowActivationRefused,
    ShadowPolicy,
    require_shadow_team,
    verify_ledger_schema,
)
from app.services.ledger_shadow.inventory import (
    INACCESSIBLE_CODES,
    ExpectedStream,
    InventoryInvalid,
    InventoryReport,
    manifest,
    resolve_expected,
    window_of,
)
from app.services.ledger_shadow.recovery import append_recovery_event, terminate_run
from app.services.ledger_shadow.staging import (
    StagingConflict,
    advance_checkpoint,
    affected_rows,
    clear_staging,
    heartbeat,
    stage_page,
    staged_lines,
)

logger = logging.getLogger(__name__)

AdapterFactory = Callable[[str, str], LedgerAdapter]


@dataclass
class RunResult:
    status: str  # published | partial | failed | retry | busy | fenced | already_terminal | disabled | not_found
    retryable: bool = False
    reason: Optional[str] = None
    report: Optional[InventoryReport] = None


@dataclass
class _StreamState:
    expected: ExpectedStream
    complete: bool = False
    error: Optional[str] = None
    retryable: bool = False
    watermark: Optional[datetime] = None


@dataclass
class _Claim:
    run_id: UUID
    attempt: int
    token: int
    max_attempts: int
    team_id: UUID
    window: DateWindow
    expected: list[ExpectedStream] = field(default_factory=list)


class ShadowSyncOrchestrator:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        adapter_factory: Optional[AdapterFactory] = None,
        policy: Optional[ShadowPolicy] = None,
    ):
        self._sessions = session_factory
        self._adapters = adapter_factory or _default_adapter
        self._policy = policy or ShadowPolicy.from_settings()

    # Requesting a run

    def create_run(self, connection_id: UUID, window: DateWindow, *, triggered_by: str = "manual") -> UUID:
        """Create or return the run for this connection. At-least-once callers get one in-flight run."""
        self._policy.require()
        team_id, provider, config = self._connection(connection_id)
        specs = self._adapters(provider, config).streams()  # may call the provider: no transaction open here
        try:
            with self._sessions() as session, session.begin():
                verify_ledger_schema(session)
                require_shadow_team(session, team_id)
                session.execute(
                    text("SELECT 1 FROM integration_connections WHERE id = :c FOR UPDATE"), {"c": connection_id}
                )
                existing = _inflight_run(session, connection_id)
                if existing is not None:
                    return existing
                expected = resolve_expected(session, team_id, connection_id, specs)
                run_id = CostLedgerService(session).start_run(connection_id, triggered_by=triggered_by)
                session.execute(
                    text("UPDATE integration_sync_runs SET metrics_json = CAST(:m AS json) WHERE id = :r"),
                    {"m": json.dumps({"ledger": {"manifest": manifest(window, expected)}}), "r": run_id},
                )
                return run_id
        except IntegrityError:
            with self._sessions() as session:  # lost a race on uq_sync_runs_inflight
                existing = _inflight_run(session, connection_id)
            if existing is None:
                raise
            return existing

    # Running an attempt

    def execute(self, run_id: UUID) -> RunResult:
        """One delivery of the task. Safe to call any number of times for the same run."""
        try:
            self._policy.require()
        except ShadowActivationRefused as refused:
            return RunResult("disabled", reason=refused.code)

        loaded = self._load(run_id)
        if isinstance(loaded, RunResult):
            return loaded
        team_id, provider, config, run_manifest = loaded

        try:
            adapter = self._adapters(provider, config)
            specs = adapter.streams()
        except AdapterConfigError as err:
            return self._refuse(run_id, err.code)
        except FetchIncomplete as err:
            return RunResult("retry", retryable=err.retryable, reason=err.code)

        claim = self._claim(run_id, team_id, specs, run_manifest)
        if isinstance(claim, RunResult):
            return claim

        report = InventoryReport()
        unknown, discovery_error, discovery_retryable, discovery_status = self._discover(adapter, claim)
        report.discovery = discovery_status
        states: Dict[UUID, _StreamState] = {}
        for expected in claim.expected:
            state = _StreamState(expected)
            states[expected.stream_id] = state
            try:
                self._fetch_stream(adapter, claim, state)
            except LedgerFenced:
                return RunResult("fenced", reason="lease_lost")

        report.expected = [e.spec.usage_account for e in claim.expected]
        report.unknown = sorted(unknown)
        report.fetched = [s.expected.spec.usage_account for s in states.values() if s.complete]
        for state in states.values():
            if state.error in INACCESSIBLE_CODES:
                report.missing.append(state.expected.spec.usage_account)
            elif state.error:
                report.failed.append(state.expected.spec.usage_account)

        transient = discovery_retryable or any(s.retryable for s in states.values())
        complete = all(s.complete for s in states.values()) and discovery_error is None
        if not complete and transient and claim.attempt < claim.max_attempts:
            return self._release_for_retry(claim, states, discovery_error)
        return self._publish(claim, states, report, discovery_error)

    def _connection(self, connection_id: UUID) -> tuple[UUID, str, str]:
        with self._sessions() as session:
            row = session.execute(
                text("SELECT team_id, provider, config_encrypted FROM integration_connections WHERE id = :c"),
                {"c": connection_id},
            ).one_or_none()
        if row is None:
            raise ShadowActivationRefused("connection_not_found")
        return row.team_id, str(row.provider), row.config_encrypted

    def _load(self, run_id: UUID):
        with self._sessions() as session:
            row = session.execute(
                text(
                    "SELECT r.phase, r.metrics_json, c.team_id, c.provider, c.config_encrypted "
                    "FROM integration_sync_runs r JOIN integration_connections c ON c.id = r.connection_id "
                    "WHERE r.id = :r AND r.pipeline = 'ledger'"
                ),
                {"r": run_id},
            ).one_or_none()
        if row is None:
            return RunResult("not_found")
        if row.phase not in ("queued", "leased", "fetching", "publishing"):
            return RunResult("already_terminal", reason=row.phase)
        run_manifest = (row.metrics_json or {}).get("ledger", {}).get("manifest")
        if not run_manifest:
            return self._refuse(run_id, "manifest_missing")
        return row.team_id, str(row.provider), row.config_encrypted, run_manifest

    def _refuse(self, run_id: UUID, reason: str) -> RunResult:
        """A closed gate or invalid inventory ends the run with a reason; it never fetches."""
        with self._sessions() as session, session.begin():
            run = session.execute(
                text("SELECT attempt, lease_token FROM integration_sync_runs WHERE id = :r FOR UPDATE"), {"r": run_id}
            ).one()
            terminate_run(session, run_id, attempt=run.attempt, token=run.lease_token, phase="failed", reason=reason)
        return RunResult("failed", reason=reason)

    def _claim(self, run_id: UUID, team_id: UUID, specs: Sequence[StreamSpec], run_manifest: Mapping[str, Any]):
        window = window_of(run_manifest)
        refusal: Optional[str] = None
        with self._sessions() as session, session.begin():
            service = CostLedgerService(session)
            try:
                verify_ledger_schema(session)
                require_shadow_team(session, team_id)
                expected = resolve_expected(session, team_id, _connection_of(session, run_id), specs)
                if manifest(window, expected)["sha256"] != run_manifest.get("sha256"):
                    raise InventoryInvalid("manifest_changed")
            except (ShadowActivationRefused, InventoryInvalid) as closed:
                refusal = closed.code
            if refusal is None:
                run = session.execute(
                    text(
                        "SELECT connection_id, attempt, max_attempts, phase FROM integration_sync_runs WHERE id = :r FOR UPDATE"
                    ),
                    {"r": run_id},
                ).one()
                if run.phase not in ("queued", "leased", "fetching", "publishing"):
                    return RunResult("already_terminal", reason=run.phase)
                attempt = run.attempt + 1
                if attempt > run.max_attempts:
                    refusal = "attempts_exhausted"
                else:
                    try:
                        token = service.acquire_lease(run_id, attempt)
                    except RunNotActive:
                        return RunResult("already_terminal")
                    if token is None:
                        return RunResult("busy", retryable=True, reason="lease_held")
                    session.execute(
                        text(
                            "UPDATE cost_sync_run_streams SET status = 'fenced', updated_at = now(), "
                            "error_code = COALESCE(error_code, 'superseded') WHERE sync_run_id = :r AND attempt < :a "
                            "AND status IN ('pending', 'fetching', 'complete')"
                        ),
                        {"r": run_id, "a": attempt},
                    )
                    session.execute(
                        text(
                            "UPDATE integration_sync_runs SET phase = 'fetching', phase_changed_at = clock_timestamp() WHERE id = :r"
                        ),
                        {"r": run_id},
                    )
                    for item in expected:
                        session.execute(
                            text(
                                "INSERT INTO cost_sync_run_streams (sync_run_id, connection_id, attempt, team_id, stream_id, "
                                "window_start, window_end, status) VALUES (:r, :c, :a, :t, :s, :ws, :we, 'pending')"
                            ),
                            {
                                "r": run_id,
                                "c": run.connection_id,
                                "a": attempt,
                                "t": team_id,
                                "s": item.stream_id,
                                "ws": window.start,
                                "we": window.end,
                            },
                        )
                    return _Claim(run_id, attempt, token, run.max_attempts, team_id, window, expected)
        return self._refuse(run_id, refusal or "refused")

    def _discover(self, adapter: LedgerAdapter, claim: _Claim):
        try:
            discovery = adapter.discover(claim.window)
        except FetchIncomplete as err:
            return set(), err.code, err.retryable, "failed"
        if not discovery.supported:
            return set(), None, False, "unsupported"
        expected = {e.spec.usage_account for e in claim.expected}
        return set(discovery.accounts) - expected, None, False, "complete"

    def _fetch_stream(self, adapter: LedgerAdapter, claim: _Claim, state: _StreamState) -> None:
        stream_id = state.expected.stream_id
        try:
            for page in adapter.fetch(state.expected.spec, claim.window):
                with self._sessions() as session, session.begin():
                    heartbeat(session, claim.run_id, claim.attempt, claim.token)
                    stage_page(session, claim.run_id, claim.attempt, stream_id, page)
                state.watermark = page.watermark or state.watermark
                if page.is_last:
                    state.complete = True
                    return
            state.error, state.retryable = "no_final_page", True
        except FetchIncomplete as err:
            state.error, state.retryable = err.code, err.retryable
        except StagingConflict:
            state.error, state.retryable = "conflicting_page", True
        except LedgerFenced:
            raise
        except Exception as err:
            # An unexpected adapter or client failure. Only the type is kept: its message could hold request details.
            logger.warning("ledger fetch failed run=%s stream=%s error=%s", claim.run_id, stream_id, type(err).__name__)
            state.error, state.retryable = "fetch_error", True
        with self._sessions() as session, session.begin():
            heartbeat(session, claim.run_id, claim.attempt, claim.token)
            session.execute(
                text(
                    "UPDATE cost_sync_run_streams SET status = 'failed', error_code = :e, updated_at = now() "
                    "WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s"
                ),
                {"e": state.error, "r": claim.run_id, "a": claim.attempt, "s": stream_id},
            )

    def _release_for_retry(
        self, claim: _Claim, states: Mapping[UUID, _StreamState], discovery_error: Optional[str]
    ) -> RunResult:
        """A recoverable attempt: publish nothing, keep the evidence, and let a newer attempt fetch again."""
        errors = sorted(
            {s.error for s in states.values() if s.error} | ({discovery_error} if discovery_error else set())
        )
        with self._sessions() as session, session.begin():
            run = session.execute(
                text("SELECT attempt, lease_token FROM integration_sync_runs WHERE id = :r FOR UPDATE"),
                {"r": claim.run_id},
            ).one()
            if (run.attempt, run.lease_token) != (claim.attempt, claim.token):
                return RunResult("fenced", reason="lease_lost")
            released = affected_rows(
                session.execute(
                    text(
                        "UPDATE cost_sync_leases SET holder_run_id = NULL, holder_attempt = NULL, expires_at = NULL "
                        "WHERE holder_run_id = :r AND holder_attempt = :a AND token = :t"
                    ),
                    {"r": claim.run_id, "a": claim.attempt, "t": claim.token},
                )
            )
            if released != 1:
                return RunResult("fenced", reason="lease_lost")
            session.execute(
                text(
                    "UPDATE cost_sync_run_streams SET status = 'fenced', error_code = 'superseded', updated_at = now() "
                    "WHERE sync_run_id = :r AND attempt = :a AND status = 'complete'"
                ),
                {"r": claim.run_id, "a": claim.attempt},
            )
            session.execute(
                text("UPDATE integration_sync_runs SET heartbeat_at = clock_timestamp() WHERE id = :r"),
                {"r": claim.run_id},
            )
            append_recovery_event(
                session, claim.run_id, {"event": "attempt_failed_retrying", "attempt": claim.attempt, "errors": errors}
            )
        return RunResult("retry", retryable=True, reason=",".join(errors))

    def _publish(
        self,
        claim: _Claim,
        states: Mapping[UUID, _StreamState],
        report: InventoryReport,
        discovery_error: Optional[str],
    ) -> RunResult:
        ready = [s for s in states.values() if s.complete]
        try:
            with self._sessions() as session, session.begin():
                service = CostLedgerService(session)
                run = session.execute(
                    text("SELECT fetch_started_at FROM integration_sync_runs WHERE id = :r FOR UPDATE"),
                    {"r": claim.run_id},
                ).one()
                for state in ready:
                    stream_id = state.expected.stream_id
                    lines = staged_lines(session, claim.run_id, claim.attempt, stream_id)
                    outcome = service.publish(
                        Publication(
                            claim.run_id,
                            claim.attempt,
                            claim.token,
                            stream_id,
                            claim.window.start,
                            claim.window.end,
                            lines,
                            True,
                        )
                    )
                    advance_checkpoint(
                        session, claim.team_id, stream_id, outcome.published_days, run.fetch_started_at, state.watermark
                    )
                    report.published.append(state.expected.spec.usage_account)
                report.incomplete = [s.expected.spec.usage_account for s in states.values() if not s.complete]
                _classify_roles(session, claim, report)
                whole = not report.incomplete and not report.unknown and discovery_error is None
                status = "success" if whole else "partial" if ready else "failed"
                service.finish_run(claim.run_id, attempt=claim.attempt, fencing_token=claim.token, status=status)
                clear_staging(session, claim.run_id)
                _record_outcome(session, claim.run_id, report, states, discovery_error, status)
        except (LedgerFenced, RunNotActive):
            return RunResult("fenced", reason="lease_lost")
        except LedgerDisabled:
            return self._refuse(claim.run_id, "team_not_in_shadow_mode")
        # Only now, after the commit, is there anything true to report
        logger.info("ledger shadow run=%s attempt=%d status=%s", claim.run_id, claim.attempt, status)
        names = {"success": "published", "partial": "partial", "failed": "failed"}
        return RunResult(names[status], report=report)


def _classify_roles(session: Session, claim: _Claim, report: InventoryReport) -> None:
    for item in claim.expected:
        account = item.spec.usage_account
        if item.spec.role == "attribution":
            report.attribution.append(account)
            continue
        authoritative = session.execute(
            text(
                "SELECT count(*) FROM cost_source_coverage WHERE authoritative_stream_id = :s AND team_id = :t "
                "AND usage_date >= :ws AND usage_date < :we"
            ),
            {"s": item.stream_id, "t": claim.team_id, "ws": claim.window.start, "we": claim.window.end},
        ).scalar_one()
        (report.authoritative if authoritative else report.witness).append(account)


def _record_outcome(
    session: Session,
    run_id: UUID,
    report: InventoryReport,
    states: Mapping[UUID, _StreamState],
    discovery_error: Optional[str],
    status: str,
) -> None:
    current = session.execute(
        text("SELECT metrics_json FROM integration_sync_runs WHERE id = :r"), {"r": run_id}
    ).scalar()
    metrics = dict(current or {})
    ledger = dict(metrics.get("ledger") or {})
    ledger["inventory"] = report.as_dict()
    metrics["ledger"] = ledger
    errors = {s.expected.spec.usage_account: s.error for s in states.values() if s.error}
    details = None
    if errors or discovery_error or report.unknown:
        details = json.dumps({"stream_errors": errors, "discovery_error": discovery_error, "unknown": report.unknown})
    session.execute(
        text(
            "UPDATE integration_sync_runs SET metrics_json = CAST(:m AS json), error_details = CAST(:d AS json) WHERE id = :r"
        ),
        {"m": json.dumps(metrics), "d": details, "r": run_id},
    )


def _inflight_run(session: Session, connection_id: UUID) -> Optional[UUID]:
    return session.execute(
        text(
            "SELECT id FROM integration_sync_runs WHERE connection_id = :c AND pipeline = 'ledger' "
            "AND phase IN ('queued', 'leased', 'fetching', 'publishing')"
        ),
        {"c": connection_id},
    ).scalar()


def _connection_of(session: Session, run_id: UUID) -> UUID:
    return session.execute(
        text("SELECT connection_id FROM integration_sync_runs WHERE id = :r"), {"r": run_id}
    ).scalar_one()


def _default_adapter(provider: str, config_encrypted: str) -> LedgerAdapter:
    from app.integrations.encryption import get_encryption
    from app.integrations.ledger.factory import build_adapter

    return build_adapter(provider, get_encryption().decrypt_config(config_encrypted))
