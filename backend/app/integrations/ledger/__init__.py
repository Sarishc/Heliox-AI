"""
Ledger ingestion adapters (Step 6F): provider fetchers for the shadow cost ledger.

Separate from ``app.integrations.providers``, whose legacy sync writes cost_snapshots and is untouched.
Adapters only read from a provider and yield normalized ``CostLine`` pages. They never touch the
database, never map a provider label or tag to a team, and never store a raw provider response.
"""
