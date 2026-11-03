"""Add the cost source ledger schema, shadow-only (no behaviour change).

Creates the tables of the idempotent cloud cost ledger designed in Step 6: source streams,
records, append-only observations, coverage and conflicts, canonical billing facts, sync
leases and staging, reconciliation, and a shadow billing ledger. It also adds metadata
columns to integration_connections, integration_sync_runs and cost_snapshots.

Nothing reads or writes these tables yet, and this migration changes no existing row:
  - every cost_snapshots amount is untouched; the new columns default to 'legacy';
  - usage_events, usage_daily_rollups and stripe_meter_exports are not touched at all;
  - every team is in ledger mode 'off' (no team_cost_ledger_settings row);
  - existing sync runs keep pipeline 'legacy' with a NULL phase, so historical stuck RUNNING
    rows cannot conflict with the new one-in-flight-run index.

Gates: the CHECK constraints named *_gate_* make live accounting impossible in the database:
no team can be 'live', no cost_snapshots row can be ledger-derived, no billing fact can be
billable, no billing ledger row can be non-shadow, and no reconciliation can be applied.
Lifting any gate needs its own, separately approved migration.

No cluster objects: no CREATE ROLE, no GRANT, no SECURITY DEFINER, no ownership change, no
extension. The trigger functions come from app.models.cost_ledger_ddl (version V1), shared
with the model DDL hooks. Upgrade runs in one transaction (Alembic on PostgreSQL); any error
rolls everything back. Locking: the ALTER TABLEs take brief ACCESS EXCLUSIVE locks on the three
existing tables (no rewrite: new columns have constant defaults) and the two new unique
constraints build indexes on integration_connections and integration_sync_runs.

Downgrade drops everything this migration added, but refuses (and changes nothing) when any
new table has rows or any new column holds a non-default value, so it can never destroy ledger
or audit data. Never downgrade a real database without a backup.

Revision ID: 038
Revises: 037
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op

from app.models.cost_ledger_ddl import (
    GUARD_FUNCTION_V1,
    GUARDED_TABLES_V1,
    RECORD_DELETE_GUARD_FUNCTION_V1,
    RECORD_DELETE_TRIGGER_V1,
    guard_trigger_v1,
)

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

# Creation order; downgrade drops in reverse
NEW_TABLES = (
    "team_cost_ledger_settings",
    "cost_source_streams",
    "cost_source_stream_bindings",
    "cost_source_authority",
    "cost_source_authority_history",
    "cost_source_stream_days",
    "cost_source_coverage",
    "cost_source_conflicts",
    "cost_source_records",
    "cost_source_observations",
    "billing_canonical_facts",
    "cost_sync_leases",
    "cost_sync_run_streams",
    "cost_sync_staging",
    "cost_source_stream_checkpoints",
    "cost_reconciliation_batches",
    "cost_reconciliation_entries",
    "cost_reconciliation_attempts",
    "billing_usage_ledger",
    "manual_cost_requests",
)

# Any of these means the new columns hold data a downgrade would destroy
NON_DEFAULT_ROWS = {
    "cost_snapshots": "source_mode <> 'legacy' OR completeness <> 'legacy' OR unconverted_count <> 0 "
    "OR ledger_updated_at IS NOT NULL",
    "integration_sync_runs": "pipeline <> 'legacy' OR phase IS NOT NULL OR attempt <> 0 OR max_attempts <> 5 "
    "OR lease_token IS NOT NULL OR dispatch_deadline_at IS NOT NULL OR heartbeat_at IS NOT NULL "
    "OR fetch_started_at IS NOT NULL OR published_at IS NOT NULL OR phase_changed_at IS NOT NULL OR billing_exempt",
    "integration_connections": "deleted_at IS NOT NULL",
}

# Reviewed DDL (docs/design/cost-ledger-6c/038_schema_v2_proposal.sql), one statement each.
# Trigger functions and triggers are added afterwards from app.models.cost_ledger_ddl.
STATEMENTS = [
    """
-- ------------------------------------------------------------------ existing tables
ALTER TABLE integration_connections ADD CONSTRAINT uq_integration_connections_team_id UNIQUE (team_id, id)
""",
    """
ALTER TABLE integration_connections ADD COLUMN deleted_at timestamptz
""",
    """
ALTER TABLE integration_sync_runs ADD CONSTRAINT uq_integration_sync_runs_id_connection UNIQUE (id, connection_id)
""",
    """
ALTER TABLE integration_sync_runs
  ADD COLUMN phase varchar(20),
  ADD COLUMN attempt integer NOT NULL DEFAULT 0,
  ADD COLUMN max_attempts integer NOT NULL DEFAULT 5,
  ADD COLUMN lease_token bigint,
  ADD COLUMN dispatch_deadline_at timestamptz,
  ADD COLUMN heartbeat_at timestamptz,
  ADD COLUMN fetch_started_at timestamptz,
  ADD COLUMN published_at timestamptz,
  ADD COLUMN phase_changed_at timestamptz,
  ADD COLUMN billing_exempt boolean NOT NULL DEFAULT false,
  ADD COLUMN pipeline varchar(8) NOT NULL DEFAULT 'legacy',
  ADD CONSTRAINT ck_sync_runs_pipeline CHECK (pipeline IN ('legacy','ledger')),
  ADD CONSTRAINT ck_sync_runs_phase CHECK (phase IS NULL OR phase IN
    ('queued','leased','fetching','publishing','published','partial','failed','abandoned','dispatch_expired')),
  ADD CONSTRAINT ck_sync_runs_phase_pipeline CHECK ((phase IS NULL) = (pipeline = 'legacy')),
  ADD CONSTRAINT ck_sync_runs_inflight_fields CHECK (
    phase IS NULL OR phase NOT IN ('leased','fetching','publishing') OR (lease_token IS NOT NULL AND fetch_started_at IS NOT NULL)),
  ADD CONSTRAINT ck_sync_runs_queued_deadline CHECK (phase IS NULL OR phase <> 'queued' OR dispatch_deadline_at IS NOT NULL)
""",
    """
CREATE UNIQUE INDEX uq_sync_runs_inflight ON integration_sync_runs (connection_id)
  WHERE phase IN ('queued','leased','fetching','publishing')
""",
    """
ALTER TABLE cost_snapshots
  ADD COLUMN source_mode varchar(8) NOT NULL DEFAULT 'legacy',
  ADD COLUMN completeness varchar(12) NOT NULL DEFAULT 'legacy',
  ADD COLUMN unconverted_count integer NOT NULL DEFAULT 0,
  ADD COLUMN ledger_updated_at timestamptz,
  ADD CONSTRAINT ck_cost_snapshots_source_mode CHECK (source_mode IN ('legacy','ledger')),
  ADD CONSTRAINT ck_cost_snapshots_completeness CHECK (
    (source_mode = 'legacy' AND completeness = 'legacy' AND unconverted_count = 0 AND ledger_updated_at IS NULL)
    OR (source_mode = 'ledger' AND completeness IN ('complete','estimated','incomplete') AND ledger_updated_at IS NOT NULL
        AND unconverted_count >= 0 AND (unconverted_count = 0 OR completeness = 'incomplete'))),
  ADD CONSTRAINT ck_cost_snapshots_gate_legacy_only CHECK (source_mode = 'legacy')
""",
    """
-- ------------------------------------------------------------------ settings
CREATE TABLE team_cost_ledger_settings (
  team_id uuid PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
  ledger_mode varchar(8) NOT NULL DEFAULT 'off',
  billing_pathway varchar(8) NOT NULL DEFAULT 'legacy',
  billing_basis varchar(24) NOT NULL DEFAULT 'legacy_saved_rows',
  changed_by uuid REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  changed_at timestamptz NOT NULL DEFAULT now(),
  reason text,
  CONSTRAINT ck_ledger_settings_values CHECK (ledger_mode IN ('off','shadow','live')
    AND billing_pathway IN ('legacy','ledger') AND billing_basis IN ('legacy_saved_rows','first_ingested')),
  CONSTRAINT ck_ledger_settings_pathway_requires_live CHECK (billing_pathway = 'legacy' OR ledger_mode = 'live'),
  CONSTRAINT ck_ledger_settings_gate_no_live CHECK (ledger_mode IN ('off','shadow')),                  -- [GATE]
  CONSTRAINT ck_ledger_settings_gate_legacy_billing CHECK (billing_pathway = 'legacy' AND billing_basis = 'legacy_saved_rows') -- [GATE]
)
""",
    """
CREATE INDEX ix_team_cost_ledger_settings_changed_by ON team_cost_ledger_settings (changed_by)
""",
    """
-- ------------------------------------------------------------------ streams
-- role 'cost' = cost-authoritative layout; role 'attribution' = reporting view only (e.g. SERVICE + TAG),
-- never authoritative, never counted, never billable
CREATE TABLE cost_source_streams (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  source_kind varchar(8) NOT NULL,
  role varchar(12) NOT NULL,
  provider varchar(32) NOT NULL,
  scope_type varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL DEFAULT '',
  usage_account varchar(160) NOT NULL,
  vantage varchar(256) NOT NULL,
  metric varchar(64) NOT NULL,
  grouping_version varchar(64) NOT NULL,
  config_sha256 bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_streams_kind CHECK (source_kind IN ('provider','manual')),
  CONSTRAINT ck_streams_role CHECK (role IN ('cost','attribution') AND (source_kind = 'provider' OR role = 'cost')),
  CONSTRAINT ck_streams_provider CHECK (provider <> '' AND provider = lower(provider)),
  CONSTRAINT ck_streams_config_sha256 CHECK (length(config_sha256) = 32),
  CONSTRAINT ck_streams_manual_scope CHECK ((source_kind = 'manual') = (scope_type = 'manual')),
  CONSTRAINT ck_streams_account_prefix CHECK (
    (source_kind = 'provider' AND usage_account LIKE provider || ':%:%')
    OR (source_kind = 'manual' AND usage_account LIKE 'manual:%')),
  CONSTRAINT uq_cost_source_streams_identity UNIQUE
    (team_id, source_kind, role, provider, scope_type, billing_account, usage_account, vantage, metric, grouping_version, config_sha256),
  CONSTRAINT uq_cost_source_streams_team_id UNIQUE (team_id, id),
  CONSTRAINT uq_cost_source_streams_team_id_kind UNIQUE (team_id, id, source_kind),
  CONSTRAINT uq_cost_source_streams_team_id_account_role UNIQUE (team_id, id, provider, billing_account, usage_account, role)
)
""",
    """
CREATE TABLE cost_source_stream_bindings (
  team_id uuid NOT NULL,
  stream_id uuid NOT NULL,
  connection_id uuid NOT NULL,
  bound_at timestamptz NOT NULL DEFAULT now(),
  unbound_at timestamptz,
  PRIMARY KEY (stream_id, connection_id),
  CONSTRAINT fk_bindings_stream FOREIGN KEY (team_id, stream_id) REFERENCES cost_source_streams (team_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_bindings_connection FOREIGN KEY (team_id, connection_id) REFERENCES integration_connections (team_id, id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT ck_bindings_interval CHECK (unbound_at IS NULL OR unbound_at >= bound_at)
)
""",
    """
CREATE INDEX ix_bindings_team_connection ON cost_source_stream_bindings (team_id, connection_id)
""",
    """
CREATE INDEX ix_bindings_team_stream ON cost_source_stream_bindings (team_id, stream_id)
""",
    """
-- Configured authority: only a cost-role stream of the same usage account
CREATE TABLE cost_source_authority (
  team_id uuid NOT NULL,
  provider varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL,
  usage_account varchar(160) NOT NULL,
  stream_id uuid NOT NULL,
  stream_role varchar(12) NOT NULL DEFAULT 'cost',
  set_by uuid NOT NULL REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  set_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL,
  PRIMARY KEY (team_id, provider, billing_account, usage_account),
  CONSTRAINT ck_authority_cost_role CHECK (stream_role = 'cost'),
  CONSTRAINT fk_authority_stream FOREIGN KEY (team_id, stream_id, provider, billing_account, usage_account, stream_role)
    REFERENCES cost_source_streams (team_id, id, provider, billing_account, usage_account, role) ON DELETE CASCADE
)
""",
    """
CREATE INDEX ix_authority_stream ON cost_source_authority (team_id, stream_id, provider, billing_account, usage_account, stream_role)
""",
    """
CREATE INDEX ix_authority_set_by ON cost_source_authority (set_by)
""",
    """
-- Every authority change is kept (append-only)
CREATE TABLE cost_source_authority_history (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  provider varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL,
  usage_account varchar(160) NOT NULL,
  from_stream_id uuid,
  to_stream_id uuid NOT NULL,
  changed_by uuid NOT NULL REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  changed_at timestamptz NOT NULL DEFAULT now(),
  reason text NOT NULL
)
""",
    """
CREATE INDEX ix_authority_history_account ON cost_source_authority_history (team_id, provider, billing_account, usage_account, changed_at)
""",
    """
CREATE INDEX ix_authority_history_changed_by ON cost_source_authority_history (changed_by)
""",
    """
-- ------------------------------------------------------------------ per stream-day and per account-day
CREATE TABLE cost_source_stream_days (
  team_id uuid NOT NULL,
  stream_id uuid NOT NULL,
  usage_date date NOT NULL,
  state varchar(16) NOT NULL,
  generation bigint NOT NULL,
  last_fetch_started_at timestamptz NOT NULL,
  last_run_id uuid NOT NULL,
  last_connection_id uuid NOT NULL,
  last_fencing_token bigint NOT NULL,
  record_count integer NOT NULL,
  converted_total_usd numeric(24,10) NOT NULL,
  unconverted_count integer NOT NULL DEFAULT 0,
  provider_total_usd numeric(24,10),
  attribution_status varchar(20),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (stream_id, usage_date),
  CONSTRAINT ck_stream_days_state CHECK (state IN ('estimated','final','suspect_empty')),
  CONSTRAINT ck_stream_days_counts CHECK (generation > 0 AND record_count >= 0 AND unconverted_count >= 0),
  CONSTRAINT ck_stream_days_attribution CHECK (attribution_status IS NULL OR attribution_status IN ('reconciled','mismatch','no_cost_coverage')),
  CONSTRAINT uq_stream_days_team UNIQUE (team_id, stream_id, usage_date),
  CONSTRAINT fk_stream_days_stream FOREIGN KEY (team_id, stream_id) REFERENCES cost_source_streams (team_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_stream_days_run FOREIGN KEY (last_run_id, last_connection_id) REFERENCES integration_sync_runs (id, connection_id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_stream_days_connection FOREIGN KEY (team_id, last_connection_id) REFERENCES integration_connections (team_id, id)
    DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_stream_days_run ON cost_source_stream_days (last_run_id, last_connection_id)
""",
    """
CREATE INDEX ix_stream_days_connection ON cost_source_stream_days (team_id, last_connection_id)
""",
    """
CREATE TABLE cost_source_coverage (
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  provider varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL,
  usage_account varchar(160) NOT NULL,
  usage_date date NOT NULL,
  authoritative_stream_id uuid NOT NULL,
  authoritative_role varchar(12) NOT NULL DEFAULT 'cost',
  state varchar(16) NOT NULL,
  authority_source varchar(20) NOT NULL,
  generation bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, provider, billing_account, usage_account, usage_date),
  CONSTRAINT ck_coverage_cost_role CHECK (authoritative_role = 'cost'),
  CONSTRAINT ck_coverage_state CHECK (state IN ('estimated','final','conflict','suspect_empty')),
  CONSTRAINT ck_coverage_authority_source CHECK (authority_source IN ('configured','default_precedence','reviewed')),
  CONSTRAINT ck_coverage_generation CHECK (generation > 0),
  CONSTRAINT fk_coverage_stream FOREIGN KEY (team_id, authoritative_stream_id, provider, billing_account, usage_account, authoritative_role)
    REFERENCES cost_source_streams (team_id, id, provider, billing_account, usage_account, role) ON DELETE CASCADE,
  CONSTRAINT fk_coverage_stream_day FOREIGN KEY (team_id, authoritative_stream_id, usage_date)
    REFERENCES cost_source_stream_days (team_id, stream_id, usage_date) ON DELETE CASCADE
)
""",
    """
CREATE INDEX ix_coverage_stream_day ON cost_source_coverage (team_id, authoritative_stream_id, usage_date)
""",
    """
CREATE INDEX ix_coverage_stream ON cost_source_coverage
  (team_id, authoritative_stream_id, provider, billing_account, usage_account, authoritative_role)
""",
    """
CREATE TABLE cost_source_conflicts (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL,
  provider varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL,
  usage_account varchar(160) NOT NULL,
  usage_date date NOT NULL,
  authoritative_stream_id uuid NOT NULL,
  witness_stream_id uuid NOT NULL,
  witness_role varchar(12) NOT NULL DEFAULT 'cost',
  authoritative_total_usd numeric(24,10),
  witness_total_usd numeric(24,10),
  status varchar(28) NOT NULL DEFAULT 'open',
  detected_run_id uuid NOT NULL,
  detected_at timestamptz NOT NULL DEFAULT now(),
  resolved_by uuid REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  resolved_at timestamptz,
  resolution_reason text,
  CONSTRAINT ck_conflicts_status CHECK (status IN ('open','resolved_keep_authoritative','resolved_switch_authority')),
  CONSTRAINT ck_conflicts_witness CHECK (witness_stream_id <> authoritative_stream_id AND witness_role = 'cost'),
  CONSTRAINT ck_conflicts_resolution CHECK ((status = 'open') = (resolved_by IS NULL AND resolved_at IS NULL AND resolution_reason IS NULL)),
  CONSTRAINT fk_conflicts_coverage FOREIGN KEY (team_id, provider, billing_account, usage_account, usage_date)
    REFERENCES cost_source_coverage (team_id, provider, billing_account, usage_account, usage_date) ON DELETE CASCADE,
  CONSTRAINT fk_conflicts_witness FOREIGN KEY (team_id, witness_stream_id, provider, billing_account, usage_account, witness_role)
    REFERENCES cost_source_streams (team_id, id, provider, billing_account, usage_account, role) ON DELETE CASCADE
)
""",
    """
CREATE UNIQUE INDEX uq_cost_source_conflicts_open ON cost_source_conflicts
  (team_id, provider, billing_account, usage_account, usage_date, witness_stream_id) WHERE status = 'open'
""",
    """
CREATE INDEX ix_conflicts_witness ON cost_source_conflicts
  (team_id, witness_stream_id, provider, billing_account, usage_account, witness_role)
""",
    """
CREATE INDEX ix_conflicts_resolved_by ON cost_source_conflicts (resolved_by)
""",
    """
-- ------------------------------------------------------------------ records and observations
CREATE TABLE cost_source_records (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL,
  stream_id uuid NOT NULL,
  source_kind varchar(8) NOT NULL,
  usage_date date NOT NULL,
  dim_1 varchar(256) NOT NULL DEFAULT '',
  dim_2 varchar(256) NOT NULL DEFAULT '',
  line_kind varchar(48) NOT NULL,
  line_key varchar(128) NOT NULL DEFAULT '',
  currency char(3) NOT NULL,
  canonical_service varchar(256) NOT NULL,
  charge_class varchar(16) NOT NULL,
  amount numeric(24,10) NOT NULL,
  amount_usd numeric(24,10),
  fx_rate numeric(24,12),
  fx_source varchar(32),
  cost_bucket varchar(100) NOT NULL,
  is_estimated boolean NOT NULL DEFAULT false,
  state varchar(8) NOT NULL DEFAULT 'present',
  absent_since_generation bigint,
  absent_at timestamptz,
  last_generation bigint NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_records_currency CHECK (length(currency) = 3 AND currency = upper(currency)),
  CONSTRAINT ck_records_charge_class CHECK (charge_class IN
    ('usage','credit','refund','discount','tax','fee','support','adjustment','rounding','other')),
  CONSTRAINT ck_records_state CHECK (
    (state = 'present' AND absent_since_generation IS NULL AND absent_at IS NULL)
    OR (state = 'absent' AND absent_since_generation IS NOT NULL AND absent_at IS NOT NULL)),
  CONSTRAINT ck_records_usd CHECK (
    (currency = 'USD' AND amount_usd = amount AND fx_rate IS NULL AND fx_source IS NULL)
    OR (currency <> 'USD' AND amount_usd IS NULL AND fx_rate IS NULL AND fx_source IS NULL)
    OR (currency <> 'USD' AND amount_usd IS NOT NULL AND fx_rate > 0 AND fx_source IS NOT NULL)),
  CONSTRAINT ck_records_canonical_service CHECK (canonical_service <> ''),
  CONSTRAINT ck_records_line_kind CHECK ((source_kind = 'manual') = (line_kind LIKE 'manual:%')),
  CONSTRAINT ck_records_manual_entry_key CHECK (source_kind = 'provider' OR line_key <> ''),
  CONSTRAINT ck_records_generation CHECK (last_generation > 0),
  CONSTRAINT uq_cost_source_records_identity UNIQUE
    (team_id, source_kind, stream_id, usage_date, dim_1, dim_2, line_kind, line_key, currency),
  CONSTRAINT uq_cost_source_records_team_id UNIQUE (team_id, id),
  CONSTRAINT fk_records_stream FOREIGN KEY (team_id, stream_id, source_kind)
    REFERENCES cost_source_streams (team_id, id, source_kind) ON DELETE CASCADE
)
""",
    """
CREATE INDEX ix_cost_source_records_bucket ON cost_source_records (team_id, usage_date, cost_bucket) WHERE state = 'present'
""",
    """
CREATE INDEX ix_cost_source_records_stream_day ON cost_source_records (stream_id, usage_date)
""",
    """
CREATE TABLE cost_source_observations (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL,
  record_id uuid NOT NULL,
  sync_run_id uuid,
  connection_id uuid,
  attempt integer,
  fencing_token bigint,
  actor_user_id uuid,
  actor_api_key_id uuid,
  generation bigint NOT NULL,
  change_kind varchar(16) NOT NULL,
  observed_amount numeric(24,10),
  observed_currency char(3) NOT NULL,
  observed_amount_usd numeric(24,10),
  previous_amount numeric(24,10),
  is_estimated boolean NOT NULL,
  payload_sha256 bytea NOT NULL,
  observed_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_obs_change_kind CHECK (change_kind IN ('inserted','corrected','unchanged','absent','reappeared','stale_ignored')),
  CONSTRAINT ck_obs_payload_sha256 CHECK (length(payload_sha256) = 32),
  CONSTRAINT ck_obs_actor CHECK (
    (sync_run_id IS NOT NULL AND connection_id IS NOT NULL AND attempt IS NOT NULL AND fencing_token IS NOT NULL
       AND actor_user_id IS NULL AND actor_api_key_id IS NULL)
    OR (sync_run_id IS NULL AND connection_id IS NULL AND attempt IS NULL AND fencing_token IS NULL
       AND ((actor_user_id IS NULL) <> (actor_api_key_id IS NULL)))),
  CONSTRAINT ck_obs_amount CHECK ((change_kind = 'absent') = (observed_amount IS NULL)),
  CONSTRAINT fk_obs_record FOREIGN KEY (team_id, record_id) REFERENCES cost_source_records (team_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_obs_connection FOREIGN KEY (team_id, connection_id) REFERENCES integration_connections (team_id, id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_obs_run FOREIGN KEY (sync_run_id, connection_id) REFERENCES integration_sync_runs (id, connection_id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_obs_user FOREIGN KEY (actor_user_id) REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_obs_api_key FOREIGN KEY (actor_api_key_id) REFERENCES team_api_keys(id) DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE UNIQUE INDEX uq_cost_source_observations_inserted ON cost_source_observations (record_id) WHERE change_kind = 'inserted'
""",
    """
CREATE INDEX ix_cost_source_observations_record ON cost_source_observations (team_id, record_id, observed_at)
""",
    """
CREATE INDEX ix_cost_source_observations_run ON cost_source_observations (sync_run_id, connection_id)
""",
    """
CREATE INDEX ix_cost_source_observations_connection ON cost_source_observations (team_id, connection_id)
""",
    """
CREATE INDEX ix_cost_source_observations_user ON cost_source_observations (actor_user_id)
""",
    """
CREATE INDEX ix_cost_source_observations_api_key ON cost_source_observations (actor_api_key_id)
""",
    """
-- ------------------------------------------------------------------ canonical billing facts
-- One row per billable expense, keyed only by what the expense is: never by connection, stream,
-- run, attempt, vantage, grouping layout or authority designation.
CREATE TABLE billing_canonical_facts (
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  provider varchar(32) NOT NULL,
  billing_account varchar(128) NOT NULL,
  usage_account varchar(160) NOT NULL,
  usage_date date NOT NULL,
  canonical_service varchar(256) NOT NULL,
  charge_class varchar(16) NOT NULL,
  currency char(3) NOT NULL,
  first_record_id uuid NOT NULL,
  first_run_id uuid,
  registered_in varchar(10) NOT NULL,
  first_billable boolean NOT NULL,
  registered_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, provider, billing_account, usage_account, usage_date, canonical_service, charge_class, currency),
  CONSTRAINT ck_facts_canonical_service CHECK (canonical_service <> ''),
  CONSTRAINT ck_facts_charge_class CHECK (charge_class IN
    ('usage','credit','refund','discount','tax','fee','support','adjustment','rounding')),
  CONSTRAINT ck_facts_registered_in CHECK (registered_in IN ('shadow','backfill','live')),
  CONSTRAINT ck_facts_billable_only_live CHECK (NOT first_billable OR registered_in = 'live'),
  CONSTRAINT ck_facts_gate_not_billable CHECK (NOT first_billable AND registered_in <> 'live'),            -- [GATE]
  CONSTRAINT fk_facts_first_record FOREIGN KEY (team_id, first_record_id) REFERENCES cost_source_records (team_id, id)
    DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_billing_canonical_facts_record ON billing_canonical_facts (team_id, first_record_id)
""",
    """
-- ------------------------------------------------------------------ sync runs, leases, staging
CREATE TABLE cost_sync_leases (
  connection_id uuid PRIMARY KEY REFERENCES integration_connections(id) ON DELETE CASCADE,
  token bigint NOT NULL DEFAULT 0,
  holder_run_id uuid,
  holder_attempt integer,
  expires_at timestamptz,
  heartbeat_at timestamptz,
  CONSTRAINT ck_leases_token CHECK (token >= 0),
  CONSTRAINT ck_leases_holder CHECK ((holder_run_id IS NULL) = (holder_attempt IS NULL AND expires_at IS NULL)),
  CONSTRAINT fk_leases_holder FOREIGN KEY (holder_run_id, connection_id) REFERENCES integration_sync_runs (id, connection_id)
    DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_leases_holder ON cost_sync_leases (holder_run_id, connection_id)
""",
    """
CREATE TABLE cost_sync_run_streams (
  sync_run_id uuid NOT NULL,
  connection_id uuid NOT NULL,
  attempt integer NOT NULL,
  team_id uuid NOT NULL,
  stream_id uuid NOT NULL,
  window_start date NOT NULL,
  window_end date NOT NULL,
  status varchar(12) NOT NULL,
  pages integer NOT NULL DEFAULT 0,
  staged_rows integer NOT NULL DEFAULT 0,
  staged_total_usd numeric(24,10) NOT NULL DEFAULT 0,
  provider_total_usd numeric(24,10),
  error_code varchar(64),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (sync_run_id, attempt, stream_id),
  CONSTRAINT ck_run_streams_status CHECK (status IN ('pending','fetching','complete','published','failed','fenced','stale')),
  CONSTRAINT ck_run_streams_attempt CHECK (attempt > 0),
  CONSTRAINT ck_run_streams_window CHECK (window_end > window_start),
  CONSTRAINT fk_run_streams_run FOREIGN KEY (sync_run_id, connection_id) REFERENCES integration_sync_runs (id, connection_id) ON DELETE CASCADE,
  CONSTRAINT fk_run_streams_stream FOREIGN KEY (team_id, stream_id) REFERENCES cost_source_streams (team_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_run_streams_connection FOREIGN KEY (team_id, connection_id) REFERENCES integration_connections (team_id, id)
    DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE UNIQUE INDEX uq_cost_sync_run_streams_published ON cost_sync_run_streams (sync_run_id, stream_id) WHERE status = 'published'
""",
    """
CREATE INDEX ix_run_streams_run ON cost_sync_run_streams (sync_run_id, connection_id)
""",
    """
CREATE INDEX ix_run_streams_stream ON cost_sync_run_streams (team_id, stream_id)
""",
    """
CREATE INDEX ix_run_streams_connection ON cost_sync_run_streams (team_id, connection_id)
""",
    """
CREATE TABLE cost_sync_staging (
  sync_run_id uuid NOT NULL,
  attempt integer NOT NULL,
  stream_id uuid NOT NULL,
  usage_date date NOT NULL,
  dim_1 varchar(256) NOT NULL DEFAULT '',
  dim_2 varchar(256) NOT NULL DEFAULT '',
  line_kind varchar(48) NOT NULL,
  line_key varchar(128) NOT NULL DEFAULT '',
  currency char(3) NOT NULL,
  canonical_service varchar(256) NOT NULL,
  charge_class varchar(16) NOT NULL,
  page_seq integer NOT NULL,
  amount numeric(24,10) NOT NULL,
  amount_usd numeric(24,10),
  fx_rate numeric(24,12),
  fx_source varchar(32),
  cost_bucket varchar(100) NOT NULL,
  is_estimated boolean NOT NULL,
  payload_sha256 bytea NOT NULL,
  PRIMARY KEY (sync_run_id, attempt, stream_id, usage_date, dim_1, dim_2, line_kind, line_key, currency),
  CONSTRAINT fk_staging_run_stream FOREIGN KEY (sync_run_id, attempt, stream_id)
    REFERENCES cost_sync_run_streams (sync_run_id, attempt, stream_id) ON DELETE CASCADE
)
""",
    """
CREATE TABLE cost_source_stream_checkpoints (
  team_id uuid NOT NULL,
  stream_id uuid PRIMARY KEY,
  final_through date,
  export_watermark timestamptz,
  last_complete_fetch_at timestamptz,
  CONSTRAINT fk_checkpoints_stream FOREIGN KEY (team_id, stream_id) REFERENCES cost_source_streams (team_id, id) ON DELETE CASCADE
)
""",
    """
CREATE INDEX ix_checkpoints_team_stream ON cost_source_stream_checkpoints (team_id, stream_id)
""",
    """
-- ------------------------------------------------------------------ reconciliation
CREATE TABLE cost_reconciliation_batches (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  date_from date NOT NULL,
  date_to date NOT NULL,
  scope jsonb NOT NULL,
  expected_inventory jsonb NOT NULL,
  status varchar(10) NOT NULL,
  proposed_by uuid NOT NULL REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  proposed_at timestamptz NOT NULL DEFAULT now(),
  approved_by uuid REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  approved_at timestamptz,
  approval_reason text,
  retire_legacy_authorized_by uuid REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  batch_fingerprint bytea NOT NULL,
  expires_at timestamptz NOT NULL,
  applied_at timestamptz,
  CONSTRAINT uq_cost_reconciliation_batches_team_id UNIQUE (team_id, id),
  CONSTRAINT ck_batches_status CHECK (status IN ('proposed','approved','applied','rejected','stale','expired')),
  CONSTRAINT ck_batches_dates CHECK (date_to >= date_from),
  CONSTRAINT ck_batches_fingerprint CHECK (length(batch_fingerprint) = 32),
  CONSTRAINT ck_batches_four_eyes CHECK (approved_by IS NULL OR approved_by <> proposed_by),
  CONSTRAINT ck_batches_approval CHECK (status NOT IN ('approved','applied') OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND approval_reason IS NOT NULL)),
  CONSTRAINT ck_batches_applied CHECK ((status = 'applied') = (applied_at IS NOT NULL)),
  CONSTRAINT ck_batches_gate_no_apply CHECK (status <> 'applied')                                         -- [GATE]
)
""",
    """
CREATE INDEX ix_batches_proposed_by ON cost_reconciliation_batches (proposed_by)
""",
    """
CREATE INDEX ix_batches_approved_by ON cost_reconciliation_batches (approved_by)
""",
    """
CREATE INDEX ix_batches_retire_by ON cost_reconciliation_batches (retire_legacy_authorized_by)
""",
    """
CREATE TABLE cost_reconciliation_entries (
  batch_id uuid NOT NULL,
  team_id uuid NOT NULL,
  usage_date date NOT NULL,
  provider varchar(100) NOT NULL,
  gpu_type varchar(100) NOT NULL,
  snapshot_id uuid NOT NULL,
  action varchar(14) NOT NULL,
  legacy_amount numeric(12,2) NOT NULL,
  ledger_amount numeric(12,2) NOT NULL,
  difference numeric(12,2) GENERATED ALWAYS AS (ledger_amount - legacy_amount) STORED,
  coverage jsonb NOT NULL,
  entry_fingerprint bytea NOT NULL,
  PRIMARY KEY (batch_id, usage_date, provider, gpu_type),
  CONSTRAINT ck_entries_action CHECK (action IN ('replace','retire_legacy') AND (action <> 'retire_legacy' OR ledger_amount = 0)),
  CONSTRAINT ck_entries_fingerprint CHECK (length(entry_fingerprint) = 32),
  CONSTRAINT fk_entries_batch FOREIGN KEY (team_id, batch_id) REFERENCES cost_reconciliation_batches (team_id, id) ON DELETE CASCADE,
  CONSTRAINT fk_entries_snapshot FOREIGN KEY (snapshot_id) REFERENCES cost_snapshots(id) DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_entries_snapshot ON cost_reconciliation_entries (snapshot_id)
""",
    """
CREATE INDEX ix_entries_batch ON cost_reconciliation_entries (team_id, batch_id)
""",
    """
CREATE TABLE cost_reconciliation_attempts (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL,
  batch_id uuid NOT NULL,
  action varchar(10) NOT NULL,
  outcome varchar(14) NOT NULL,
  actor_user_id uuid NOT NULL REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  reason text,
  expected_fingerprint bytea,
  actual_fingerprint bytea,
  details jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_attempts_action CHECK (action IN ('propose','approve','reject','apply')),
  CONSTRAINT ck_attempts_outcome CHECK (outcome IN ('ok','stale','incomplete','unauthorized','expired','error')),
  CONSTRAINT fk_attempts_batch FOREIGN KEY (team_id, batch_id) REFERENCES cost_reconciliation_batches (team_id, id) ON DELETE CASCADE
)
""",
    """
CREATE INDEX ix_attempts_batch ON cost_reconciliation_attempts (team_id, batch_id)
""",
    """
CREATE INDEX ix_attempts_actor ON cost_reconciliation_attempts (actor_user_id)
""",
    """
-- ------------------------------------------------------------------ billing usage ledger (shadow only in 038)
CREATE TABLE billing_usage_ledger (
  id uuid PRIMARY KEY,
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  event_type varchar(32) NOT NULL,
  idempotency_key varchar(200) NOT NULL,
  basis varchar(24) NOT NULL,
  quantity bigint NOT NULL,
  shadow boolean NOT NULL,
  billing_exempt boolean NOT NULL DEFAULT false,
  sync_run_id uuid,
  connection_id uuid,
  stream_id uuid,
  accrual_date date NOT NULL,
  usage_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_usage_ledger_basis CHECK (basis IN ('legacy_saved_rows','first_ingested')),
  CONSTRAINT ck_usage_ledger_quantity CHECK (quantity >= 0),
  CONSTRAINT ck_usage_ledger_no_event_when_shadow CHECK (NOT (shadow AND usage_event_id IS NOT NULL)),
  CONSTRAINT ck_usage_ledger_no_event_when_exempt CHECK (NOT (billing_exempt AND usage_event_id IS NOT NULL)),
  CONSTRAINT ck_usage_ledger_gate_shadow_only CHECK (shadow AND usage_event_id IS NULL),                    -- [GATE]
  CONSTRAINT uq_billing_usage_ledger_key UNIQUE (idempotency_key, basis),
  CONSTRAINT fk_usage_ledger_run FOREIGN KEY (sync_run_id, connection_id) REFERENCES integration_sync_runs (id, connection_id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_usage_ledger_connection FOREIGN KEY (team_id, connection_id) REFERENCES integration_connections (team_id, id)
    DEFERRABLE INITIALLY DEFERRED,
  CONSTRAINT fk_usage_ledger_stream FOREIGN KEY (team_id, stream_id) REFERENCES cost_source_streams (team_id, id)
    DEFERRABLE INITIALLY DEFERRED
)
""",
    """
CREATE INDEX ix_usage_ledger_run ON billing_usage_ledger (sync_run_id, connection_id)
""",
    """
CREATE INDEX ix_usage_ledger_connection ON billing_usage_ledger (team_id, connection_id)
""",
    """
CREATE INDEX ix_usage_ledger_stream ON billing_usage_ledger (team_id, stream_id)
""",
    """
CREATE TABLE manual_cost_requests (
  team_id uuid NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  idempotency_key varchar(128) NOT NULL,
  request_sha256 bytea NOT NULL,
  response_status smallint NOT NULL,
  response_body jsonb NOT NULL,
  actor_user_id uuid REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED,
  actor_api_key_id uuid REFERENCES team_api_keys(id) DEFERRABLE INITIALLY DEFERRED,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (team_id, idempotency_key),
  CONSTRAINT ck_manual_requests_actor CHECK ((actor_user_id IS NULL) <> (actor_api_key_id IS NULL))
)
""",
    """
CREATE INDEX ix_manual_requests_user ON manual_cost_requests (actor_user_id)
""",
    """
CREATE INDEX ix_manual_requests_api_key ON manual_cost_requests (actor_api_key_id)
""",
]


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        ).scalar()
    )


def _check_037_schema(conn) -> None:
    present = [t for t in NEW_TABLES if conn.execute(sa.text("SELECT to_regclass(:t)"), {"t": t}).scalar()]
    added = [
        f"{table}.{column}"
        for table, column in (
            ("cost_snapshots", "source_mode"),
            ("integration_sync_runs", "phase"),
            ("integration_connections", "deleted_at"),
        )
        if _column_exists(conn, table, column)
    ]
    if present or added:
        raise RuntimeError(f"038 refused: schema is not what 037 left (already present: {present + added})")


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name != "postgresql":
        raise RuntimeError("038 supports PostgreSQL only")
    _check_037_schema(conn)
    for statement in STATEMENTS:
        op.execute(sa.text(statement))
    op.execute(sa.text(GUARD_FUNCTION_V1))
    op.execute(sa.text(RECORD_DELETE_GUARD_FUNCTION_V1))
    for table in GUARDED_TABLES_V1:
        op.execute(sa.text(guard_trigger_v1(table)))
    op.execute(sa.text(RECORD_DELETE_TRIGGER_V1))


def _ledger_data(conn) -> list[str]:
    found = []
    for table in NEW_TABLES:
        rows = conn.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
        if rows:
            found.append(f"{table}: {rows} row(s)")
    for table, condition in NON_DEFAULT_ROWS.items():
        rows = conn.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {condition}")).scalar()
        if rows:
            found.append(f"{table}: {rows} row(s) with ledger values")
    return found


def downgrade() -> None:
    conn = op.get_bind()
    found = _ledger_data(conn)
    if found:
        raise RuntimeError("038 downgrade refused, it would destroy ledger or audit data: " + "; ".join(found))
    for table in reversed(NEW_TABLES):
        op.execute(sa.text(f"DROP TABLE {table}"))
    op.execute(sa.text("DROP FUNCTION cost_audit_guard()"))
    op.execute(sa.text("DROP FUNCTION cost_record_delete_guard()"))
    op.execute(sa.text("DROP INDEX uq_sync_runs_inflight"))
    op.execute(
        sa.text(
            "ALTER TABLE integration_sync_runs "
            "DROP CONSTRAINT ck_sync_runs_queued_deadline, DROP CONSTRAINT ck_sync_runs_inflight_fields, "
            "DROP CONSTRAINT ck_sync_runs_phase_pipeline, DROP CONSTRAINT ck_sync_runs_phase, "
            "DROP CONSTRAINT ck_sync_runs_pipeline, DROP CONSTRAINT uq_integration_sync_runs_id_connection, "
            "DROP COLUMN pipeline, DROP COLUMN billing_exempt, DROP COLUMN phase_changed_at, DROP COLUMN published_at, "
            "DROP COLUMN fetch_started_at, DROP COLUMN heartbeat_at, DROP COLUMN dispatch_deadline_at, "
            "DROP COLUMN lease_token, DROP COLUMN max_attempts, DROP COLUMN attempt, DROP COLUMN phase"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE integration_connections "
            "DROP CONSTRAINT uq_integration_connections_team_id, DROP COLUMN deleted_at"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE cost_snapshots "
            "DROP CONSTRAINT ck_cost_snapshots_gate_legacy_only, DROP CONSTRAINT ck_cost_snapshots_completeness, "
            "DROP CONSTRAINT ck_cost_snapshots_source_mode, DROP COLUMN ledger_updated_at, "
            "DROP COLUMN unconverted_count, DROP COLUMN completeness, DROP COLUMN source_mode"
        )
    )
