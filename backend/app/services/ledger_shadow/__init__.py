"""
Shadow cost-ledger orchestration (Step 6F), on the migration 038 tables.

    provider adapter -> normalized lines -> cost_sync_staging -> completeness validation
    -> fenced CostLedgerService.publish -> coverage and checkpoint update -> shadow reconciliation

Disabled by default and shadow-only. It never writes cost_snapshots, usage_events, usage_daily_rollups
or stripe_meter_exports, and has no production caller or Beat schedule. See
docs/COST_LEDGER_SHADOW_ORCHESTRATION.md for the contract.
"""
