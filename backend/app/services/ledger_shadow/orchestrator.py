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

from app.integrations.ledger.base import (
    DAY_ESTIMATED,
    DAY_FINAL,
    AdapterConfigError,
    DateWindow,
    FetchIncomplete,
    LedgerAdapter,
    ScopeVerdict,
    StreamSpec,
)
from app.services.cost_ledger import (
    CostLedgerService,
    LedgerDisabled,
    LedgerFenced,
    Publication,
    RunNotActive,
    TenantMismatch,
)
from app.services.ledger_shadow.activation import (
    ShadowActivationRefused,
    ShadowPolicy,
    require_eligible_connection,
    require_shadow_team,
    verify_ledger_schema,
)
from app.services.ledger_shadow.inventory import (
    AMBIGUOUS_SOURCE,
    INACCESSIBLE_CODES,
    ExpectedStream,
    InventoryInvalid,
    InventoryReport,
    ambiguous_streams,
    manifest,
    resolve_expected,
    window_of,
)
from app.services.ledger_shadow.recovery import append_recovery_event, terminate_run
from app.services.ledger_shadow.staging import (
    MissingPage,
    StagingConflict,
    affected_rows,
    clear_staging,
    heartbeat,
    record_complete_fetch,
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
    evidence: Optional[Mapping[Any, str]] = None


@dataclass
class _Claim:
    run_id: UUID
    attempt: int
    token: int
    max_attempts: int
    team_id: UUID
    window: DateWindow
    expected: list[ExpectedStream] = field(default_factory=list)
    ambiguous: set[UUID] = field(default_factory=set)


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

    def create_run(
        self, team_id: UUID, connection_id: UUID, window: DateWindow, *, triggered_by: str = "manual"
    ) -> UUID:
        """Create or return the run for this team's connection. At-least-once callers get one in-flight run."""
        self._policy.require()
        with self._sessions() as session:
            connection = require_eligible_connection(session, connection_id, team_id)
        # May call the provider, so no transaction is open here. Everything above refused first.
        specs = self._adapters(str(connection.provider), connection.config_encrypted).streams()
        try:
            with self._sessions() as session, session.begin():
                verify_ledger_schema(session)
                require_shadow_team(session, team_id)
                session.execute(
                    text("SELECT 1 FROM integration_connections WHERE id = :c FOR UPDATE"), {"c": connection_id}
                )
                require_eligible_connection(session, connection_id, team_id)
                existing = _inflight_run(session, connection_id)
                if existing is not None:
                    return existing
                expected = resolve_expected(session, team_id, connection_id, specs)
                run_id = CostLedgerService(session).start_run(connection_id, triggered_by=triggered_by)
                session.execute(
                    text("UPDATE integration_sync_runs SET metrics_json = CAST(:m AS json) WHERE id = :r"),
                    {
                        "m": json.dumps({"ledger": {"team_id": str(team_id), "manifest": manifest(window, expected)}}),
                        "r": run_id,
                    },
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
        verdicts = self._verify_scope(adapter)
        unknown, discovery_error, discovery_retryable, discovery_status = self._discover(adapter, claim)
        report.discovery = discovery_status
        states: Dict[UUID, _StreamState] = {}
        for expected in claim.expected:
            state = _StreamState(expected)
            states[expected.stream_id] = state
            account = expected.spec.usage_account
            verdict = verdicts.get(account, ScopeVerdict(False, "scope_not_reported"))
            try:
                if expected.stream_id in claim.ambiguous:
                    report.ambiguous.append(account)
                    state.error = AMBIGUOUS_SOURCE
                    self._fail_stream(claim, state)
                elif not verdict.verified:
                    report.scope_unverified.append(account)
                    state.error, state.retryable = verdict.code or "scope_unverified", verdict.retryable
                    self._fail_stream(claim, state)
                else:
                    self._fetch_stream(adapter, claim, state)
            except LedgerFenced:
                return RunResult("fenced", reason="lease_lost")

        report.expected = [e.spec.usage_account for e in claim.expected]
        report.unknown = sorted(unknown)
        report.fetched = [s.expected.spec.usage_account for s in states.values() if s.complete]
        for state in states.values():
            account = state.expected.spec.usage_account
            if state.error in INACCESSIBLE_CODES or account in report.scope_unverified:
                report.missing.append(state.expected.spec.usage_account)
            elif state.error:
                report.failed.append(state.expected.spec.usage_account)

        transient = discovery_retryable or any(s.retryable for s in states.values())
        complete = all(s.complete for s in states.values()) and discovery_error is None
        if not complete and transient and claim.attempt < claim.max_attempts:
            return self._release_for_retry(claim, states, discovery_error)
        return self._publish(claim, states, report, discovery_error)

    def _load(self, run_id: UUID):
        """Everything here is checked before any adapter exists, so a refusal cannot reach a provider."""
        with self._sessions() as session:
            row = session.execute(
                text(
                    "SELECT r.phase, r.connection_id, r.metrics_json FROM integration_sync_runs r "
                    "WHERE r.id = :r AND r.pipeline = 'ledger'"
                ),
                {"r": run_id},
            ).one_or_none()
            connection = None
            refusal = None
            if row is not None and row.phase in ("queued", "leased", "fetching", "publishing"):
                ledger = (row.metrics_json or {}).get("ledger", {})
                try:
                    connection = require_eligible_connection(session, row.connection_id, UUID(ledger["team_id"]))
                except (KeyError, ValueError):
                    refusal = "manifest_missing"
                except ShadowActivationRefused as closed:
                    refusal = closed.code
        if row is None:
            return RunResult("not_found")
        if row.phase not in ("queued", "leased", "fetching", "publishing"):
            return RunResult("already_terminal", reason=row.phase)
        if refusal is not None:
            return self._refuse(run_id, refusal)
        if connection is None:
            return RunResult("not_found")
        run_manifest = ledger.get("manifest")
        if not run_manifest:
            return self._refuse(run_id, "manifest_missing")
        return connection.team_id, str(connection.provider), connection.config_encrypted, run_manifest

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
                connection_id = _connection_of(session, run_id)
                require_eligible_connection(session, connection_id, team_id)
                expected = resolve_expected(session, team_id, connection_id, specs)
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
                    ambiguous = ambiguous_streams(session, [e.stream_id for e in expected])
                    return _Claim(run_id, attempt, token, run.max_attempts, team_id, window, expected, ambiguous)
        return self._refuse(run_id, refusal or "refused")

    def _verify_scope(self, adapter: LedgerAdapter) -> Mapping[str, ScopeVerdict]:
        """Fail closed: a lookup that errors verifies nothing. The error text is never kept."""
        try:
            return adapter.verify_scope()
        except FetchIncomplete as err:
            everything = ScopeVerdict(False, err.code, err.retryable)
        except Exception as err:
            logger.warning("ledger scope verification failed error=%s", type(err).__name__)
            everything = ScopeVerdict(False, "scope_lookup_failed", True)
        return _AllAccounts(everything)

    def _discover(self, adapter: LedgerAdapter, claim: _Claim):
        try:
            discovery = adapter.discover(claim.window)
        except FetchIncomplete as err:
            return set(), err.code, err.retryable, "failed"
        except Exception as err:
            logger.warning("ledger discovery failed run=%s error=%s", claim.run_id, type(err).__name__)
            return set(), "discovery_failed", True, "failed"
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
                    state.evidence = page.day_evidence
                    return
            state.error, state.retryable = "no_final_page", True
        except FetchIncomplete as err:
            state.error, state.retryable = err.code, err.retryable
        except StagingConflict:
            state.error, state.retryable = "conflicting_page", True
        except MissingPage:
            state.error, state.retryable = "missing_page", True
        except LedgerFenced:
            raise
        except Exception as err:
            # An unexpected adapter or client failure. Only the type is kept: its message could hold request details.
            logger.warning("ledger fetch failed run=%s stream=%s error=%s", claim.run_id, stream_id, type(err).__name__)
            state.error, state.retryable = "fetch_error", True
        self._fail_stream(claim, state)

    def _fail_stream(self, claim: _Claim, state: _StreamState) -> None:
        stream_id = state.expected.stream_id
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
        try:
            with self._sessions() as session, session.begin():
                service = CostLedgerService(session)
                run = session.execute(
                    text("SELECT connection_id, fetch_started_at FROM integration_sync_runs WHERE id = :r FOR UPDATE"),
                    {"r": claim.run_id},
                ).one()
                # State can change during a fetch: a connection disabled or a source claimed since the claim stops here
                require_eligible_connection(session, run.connection_id, claim.team_id)
                ambiguous = ambiguous_streams(session, [s.expected.stream_id for s in states.values() if s.complete])
                ready = []
                for state in states.values():
                    if state.complete and not _staged_completely(session, claim, state, ambiguous):
                        state.complete = False
                        report.fetched = [a for a in report.fetched if a != state.expected.spec.usage_account]
                    if state.complete:
                        ready.append(state)
                for state in ready:
                    stream_id = state.expected.stream_id
                    lines = staged_lines(session, claim.run_id, claim.attempt, stream_id)
                    evidence = state.evidence or {}  # no evidence proves nothing about an empty day
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
                            estimated_days=frozenset(d for d in claim.window.days if evidence.get(d) == DAY_ESTIMATED),
                            unproven_days=frozenset(
                                d for d in claim.window.days if evidence.get(d) not in (DAY_FINAL, DAY_ESTIMATED)
                            ),
                        )
                    )
                    if outcome.unproven_days:
                        report.unproven_days[state.expected.spec.usage_account] = [
                            d.isoformat() for d in outcome.unproven_days
                        ]
                    if outcome.invalidated_claims:
                        report.invalidated_claims[state.expected.spec.usage_account] = outcome.invalidated_claims
                    record_complete_fetch(session, claim.team_id, stream_id, run.fetch_started_at, state.watermark)
                    report.published.append(state.expected.spec.usage_account)
                report.incomplete = [s.expected.spec.usage_account for s in states.values() if not s.complete]
                _classify_roles(session, claim, report)
                whole = (
                    not report.incomplete
                    and not report.unknown
                    and not report.unproven_days
                    and discovery_error is None
                )
                status = "success" if whole else "partial" if ready else "failed"
                service.finish_run(claim.run_id, attempt=claim.attempt, fencing_token=claim.token, status=status)
                clear_staging(session, claim.run_id)
                _record_outcome(session, claim.run_id, report, states, discovery_error, status)
        except (LedgerFenced, RunNotActive):
            return RunResult("fenced", reason="lease_lost")
        except LedgerDisabled:
            return self._refuse(claim.run_id, "team_not_in_shadow_mode")
        except ShadowActivationRefused as closed:
            return self._refuse(claim.run_id, closed.code)
        except TenantMismatch:
            return self._refuse(claim.run_id, "stream_unbound")
        # Only now, after the commit, is there anything true to report
        logger.info("ledger shadow run=%s attempt=%d status=%s", claim.run_id, claim.attempt, status)
        names = {"success": "published", "partial": "partial", "failed": "failed"}
        return RunResult(names[status], report=report)


class _AllAccounts(dict):
    """One verdict for every account, when the provider could not be asked at all."""

    def __init__(self, verdict: ScopeVerdict):
        super().__init__()
        self.verdict = verdict

    def get(self, key, default=None):
        return self.verdict


def _staged_completely(session: Session, claim: _Claim, state: _StreamState, ambiguous: set[UUID]) -> bool:
    """A final-page marker in memory is not enough: the durable progress row must agree. Marks a refusal as failed."""
    stream_id = state.expected.stream_id
    progress = session.execute(
        text(
            "SELECT rs.status, rs.pages, rs.staged_rows, (SELECT count(*) FROM cost_sync_staging x "
            "WHERE x.sync_run_id = rs.sync_run_id AND x.attempt = rs.attempt AND x.stream_id = rs.stream_id) AS staged "
            "FROM cost_sync_run_streams rs WHERE rs.sync_run_id = :r AND rs.attempt = :a AND rs.stream_id = :s"
        ),
        {"r": claim.run_id, "a": claim.attempt, "s": stream_id},
    ).one_or_none()
    if stream_id in ambiguous:
        state.error = AMBIGUOUS_SOURCE
    elif (
        progress is None
        or progress.status != "complete"
        or progress.pages < 1
        or progress.staged != progress.staged_rows
    ):
        state.error = "stream_not_complete"
    else:
        return True
    session.execute(
        text(
            "UPDATE cost_sync_run_streams SET status = 'failed', error_code = :e, updated_at = now() "
            "WHERE sync_run_id = :r AND attempt = :a AND stream_id = :s"
        ),
        {"e": state.error, "r": claim.run_id, "a": claim.attempt, "s": stream_id},
    )
    return False


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
        if authoritative:
            report.authoritative.append(account)
        elif _has_published_days(session, claim, item.stream_id):
            report.witness.append(account)


def _has_published_days(session: Session, claim: _Claim, stream_id: UUID) -> bool:
    return bool(
        session.execute(
            text(
                "SELECT 1 FROM cost_source_stream_days WHERE stream_id = :s AND usage_date >= :a AND usage_date < :b LIMIT 1"
            ),
            {"s": stream_id, "a": claim.window.start, "b": claim.window.end},
        ).scalar()
    )


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

    try:
        config = get_encryption().decrypt_config(config_encrypted)
    except ValueError:
        raise AdapterConfigError("credentials_unreadable") from None
    return build_adapter(provider, config)
