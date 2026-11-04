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
| Publish | Eligibility and ambiguity re-checked; for all complete streams: `publish`, checkpoint row, then `finish_run` and clearing staging |

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

## Scope verification

A stream with no rows is a confirmed zero only if the provider itself proves the account belongs to this source, independently of cost rows. `verify_scope` runs after the claim and before any cost query. Whatever it doesn't prove is failed with a reason: no coverage, no stream day, no checkpoint.

| Provider | What proves membership | Permission | What it can't prove |
|---|---|---|---|
| AWS | `DescribeOrganization.MasterAccountId` must equal the configured payer; `ListAccounts` must list the account with `State = ACTIVE` | Any account can call the first; only the management account or a delegated administrator can call the second | A member connection proves only itself. A payer without `ListAccounts` proves only itself |
| GCP | `projects.getBillingInfo`: `billingAccountName` matches and `billingEnabled` is true | `resourcemanager.projects.get` on each project | A project that moved reads as moved, even for days it was still on this account |
| Azure, subscription scope | `Subscriptions - Get` with state Enabled, Warned or PastDue | Read on the subscription | No billing relationship is claimed |
| Azure, billing scope | The billing account's `billingSubscriptions` list contains the subscription | Billing reader | Accounts or agreement types whose list omits `subscriptionId` are unverified |

AWS `SUSPENDED` accounts and disabled GCP projects are refused even though they may have historical cost. This fails closed on purpose: such a day stays unknown rather than wrong.

## Source identity and overlap

Coverage is keyed by billing account, so a second view counts once only when both name the same bill.

- **AWS:** the billing account is the payer, and verification requires AWS to confirm it, so a connection claiming a different payer stops at `payer_mismatch`.
- **Azure:** `billing_account` is empty because a subscription id is globally unique. Subscription and billing scopes are therefore witnesses of each other.
- **GCP:** a copied export is a witness, because table name is only the vantage.
- **Any provider:** if two active streams in a team claim one usage account under different billing accounts, both are quarantined as `source_identity_ambiguous`, and totals already published for that account read as incomplete. Nothing chooses a winner. A person resolves it by unbinding the wrong connection. `cost_source_authority` is per billing account, so it can't arbitrate this; doing so needs a schema change.

## Inventory

Migration 038 can hold the inventory, so no new table was needed:

- **Expected streams:** active `cost_source_stream_bindings` rows, declared explicitly by `configure_inventory`.
- **Per run:** a manifest digest in `metrics_json`, and one `cost_sync_run_streams` row per expected stream per attempt.
- **Result:** the `InventoryReport` in `metrics_json` keeps expected, fetched, missing, failed, published, incomplete, unknown, witness, attribution and authoritative accounts apart.

A difference between configuration and bindings blocks the run. So does an empty inventory. An account with no rows is a confirmed zero only if its fetch completed. Unknown accounts are reported, get no stream, and keep the run from being a full success.

AWS member callers and Azure subscription scopes can't list their siblings. Where discovery isn't supported, `discovery` is recorded as `unsupported`, and only the declared inventory is checked. Discovery reports accounts with spend; it does not prove membership, which is what scope verification is for.

## Checkpoints

`cost_source_stream_checkpoints.final_through` stays NULL. Migration 038 stores no starting boundary, so any value there would read as "every earlier day is final", even for a stream first fetched yesterday. The row records only `last_complete_fetch_at` and `export_watermark`, in the publish transaction.

`stream_coverage(session, stream_id, window)` answers the question with an explicit start. It reports each day separately: fetched or missing, provider state, and financial state. `final_through` and `financially_complete_through` in its result are proven from that start and stop at the first gap. Persisting this needs a later migration that adds a coverage start per stream.

## Enrollment

`enroll_connection` and `revoke_connection` are private, with no route. Enrollment requires an owner or admin of the team, a non-blank reason, a team already in shadow mode, an eligible connection, verified scope for every account, no run in flight and no ambiguous source. Changes are written to `audit_logs`. Revoking unbinds the streams, keeps history, and makes the next attempt of any in-flight run stop.

## Connection eligibility

Only `status = 'active'` with `deleted_at` NULL and stored credentials may run; the model has no separate "revoked" state. `pending`, `error` and `disabled` are refused. This is checked before any provider call, again in the claim, and again in the publish transaction.

## Provider contracts

Request and response mappings were compared with the published API references on 2026-11-03. Fake clients prove only this side of each contract.

**Not verified against a real provider:**

- Whether BigQuery accepts the SQL. It has never been parsed by BigQuery; a credentialed dry-run needs separate authorization.
- The stored spelling of GCP's rounding `cost_type`. The docs say "rounding error"; both spellings are accepted.
- `DATE(usage_start_time)` uses UTC. The docs state no timezone for usage days, so days may differ from the billing console.
- Azure result column names (`Cost`, `CostUSD`, `UsageDate`, `Currency`) and that `Currency` is returned without being grouped. A missing column fails closed.
- Whether Azure's `to` is inclusive. It isn't documented, so the request names the last second of the last day.
- AWS `RECORD_TYPE` values, which aren't enumerated. Unknown values stay visible as `other`. AWS account `State` values beyond `ACTIVE`, which aren't listed; anything else is refused.
- Whether a day with no groups reports a zero `Total` in Cost Explorer. A non-zero one fails closed.
- Azure `204` from the query API, which is documented but undefined. It fails closed, so a provider using it for "no cost" would never complete.

## Fencing and recovery

Every write checks the run's attempt and token against the lease. An expired lease is never revived. `reap_abandoned_runs` skips live leases and locked runs. An expired lease only makes a run eligible for a newer attempt, because it says nothing about the provider. Runs with no attempts left end as `abandoned`, undispatched runs as `dispatch_expired`, both with a structured reason. The trail is in `metrics_json.ledger.recovery`.

## Activation

All of these are required:

1. `LEDGER_SHADOW_WORKER_ENABLED=true`. Without it the tasks aren't even registered.
2. `ENV` is `dev` or `staging`, never `production`.
3. The team's ledger mode is `shadow`. Nothing enrolls a team automatically.
4. An eligible connection with valid provider configuration.
5. All six migration 038 gate constraints exist.
6. A valid, non-empty inventory.

Nothing schedules or enqueues the tasks, and the flag cannot enable billing: the database gates forbid it.

## Known limits under migration 038

- `metrics_json` is a JSON column on the run row, so the recovery trail is append-by-rewrite under the run lock, not an append-only table.
- `final_through` can't be used safely (see Checkpoints). `stream_coverage` and `coverage_completeness` report the state instead.
- The ambiguity between billing accounts can't be recorded as a conflict row, because `cost_source_conflicts` requires both streams to share a billing account. It's computed from active bindings when read.
- Previous non-amount values of a correction survive only as a digest in the observation.
- The manifest stores the accounts requested for a run, but the configuration behind a stream is stored only as a digest.
