# Cost ledger shadow orchestration

Contract for the Step 6F shadow ingestion path. It is off by default, shadow-only, and has no production caller or schedule.

```
Provider adapter -> normalized CostLine pages -> cost_sync_staging -> completeness validation
  -> fenced CostLedgerService.publish -> coverage and checkpoint update -> shadow reconciliation
```

## Transaction boundaries

No database transaction is open during a provider call.

| Step | Transaction contains |
|---|---|
| Request | Activation gates, inventory check, `start_run`, deterministic manifest in `metrics_json` |
| Claim | Run row lock, newer attempt, fenced lease, one `pending` progress row per expected stream |
| Each page | Heartbeat (which fences a stale attempt), idempotent staging, progress update |
| Publish | For all complete streams: `publish`, checkpoint, then `finish_run` and clearing staging |

The publish step commits together or not at all. A crash before the commit leaves nothing accepted, and the retry fetches again. A crash after the commit makes the redelivered task a no-op, because the run is terminal. No event or log claims success before the commit.

Lock order everywhere is run row, then lease row, then team advisory lock.

## Retry policy

| Situation | Result |
|---|---|
| Lease held by a live worker | `busy`; no attempt consumed; task retries with backoff |
| Retryable failure with attempts left | Nothing is published; lease released; next delivery takes a newer attempt |
| Non-retryable failure (inaccessible account, malformed data) | Complete streams are published; the run ends `partial`, or `failed` if none were complete |
| Attempts exhausted | The complete streams are published and the run ends `partial` or `failed` |
| Lost lease | `fenced`; the attempt stops and writes nothing more |
| Run already terminal | No-op |

Task backoff is exponential with jitter: 30 seconds doubling up to 15 minutes, at most 5 redeliveries.

A retry always fetches again rather than reusing an earlier attempt's staging. Reusing it would publish old data under a newer `fetch_started_at`, and staleness protection depends on that timestamp. Earlier staging stays as evidence until the run is terminal.

## Stream identity

A stream is (team, source kind, role, provider, scope type, billing account, usage account, vantage, metric, grouping version, configuration digest). It holds no credentials.

| Provider | Usage account | Vantage | Scope |
|---|---|---|---|
| AWS | `aws:acct:<id>` | `aws:caller:<caller id>` | one query per linked account, grouped by service and record type |
| GCP | `gcp:project:<id>`, plus one stream for rows with no project | `gcp:table:<table>` | one query per project, standard or detailed export |
| Azure | `azure:sub:<id>` | `azure:scope:<scope>` | subscription scope, or one billing-account scope filtered per subscription |

A second view of the same account has a different vantage, so the ledger treats it as a witness and it never adds to totals. This only works if both views name the same coverage key (provider, billing account, usage account). Azure therefore leaves `billing_account` empty, because a subscription id is globally unique, and keeps the billing account in the vantage.

## Completeness guarantees by provider

A stream is complete only when the adapter yields a page with `is_last`, which happens after all of the following:

- **AWS:** every `NextPageToken` is followed; a repeated token, a failed page or an absent day in the window makes it incomplete. A payer caller is authoritative for its linked accounts. A member caller can only claim itself.
- **GCP:** every result page is read and the row count matches `total_rows`. The export's latest `export_time` must have passed the window end, otherwise a silent day proves nothing.
- **Azure:** every `nextLink` is followed, only over HTTPS to `management.azure.com` within the same scope. 401 refreshes the token once; 429 and 5xx retry a bounded number of times. 401 after a refresh, 403 and 404 mean the subscription is inaccessible, never zero.

## Inventory

Migration 038 can hold the inventory, so no new table was needed:

- **Expected streams:** active `cost_source_stream_bindings` rows, declared explicitly by `configure_inventory`.
- **Per run:** a manifest digest in `metrics_json`, and one `cost_sync_run_streams` row per expected stream per attempt.
- **Result:** the `InventoryReport` in `metrics_json` keeps expected, fetched, missing, failed, published, incomplete, unknown, witness, attribution and authoritative accounts apart.

A difference between configuration and bindings blocks the run. So does an empty inventory. An account with no rows is a confirmed zero only if its fetch completed. Unknown accounts are reported, get no stream, and keep the run from being a full success.

AWS member callers and Azure subscription scopes can't list their siblings. Where discovery isn't supported, `discovery` is recorded as `unsupported`, and only the declared inventory is checked.

## Fencing and recovery

Every write checks the run's attempt and token against the lease. An expired lease is never revived. `reap_abandoned_runs` skips live leases and locked runs. An expired lease only makes a run eligible for a newer attempt, because it says nothing about the provider. Runs with no attempts left end as `abandoned`, undispatched runs as `dispatch_expired`, both with a structured reason. The trail is in `metrics_json.ledger.recovery`.

## Activation

All of these are required:

1. `LEDGER_SHADOW_WORKER_ENABLED=true`. Without it the tasks aren't even registered.
2. `ENV` is `dev` or `staging`, never `production`.
3. The team's ledger mode is `shadow`. Nothing enrolls a team automatically.
4. A valid provider configuration.
5. All six migration 038 gate constraints exist.
6. A valid, non-empty inventory.

Nothing schedules or enqueues the tasks, and the flag cannot enable billing: the database gates forbid it.

## Known limits under migration 038

- `metrics_json` is a JSON column on the run row, so the recovery trail is append-by-rewrite under the run lock, not an append-only table.
- `final_through` tracks fetch finality, not financial finality. `coverage_completeness` is what reports financial state.
- Previous non-amount values of a correction survive only as a digest in the observation.
- The manifest stores the accounts requested for a run, but the configuration behind a stream is stored only as a digest.
