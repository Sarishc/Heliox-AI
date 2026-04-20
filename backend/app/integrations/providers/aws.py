"""
AWS Cost Explorer integration.

The real implementation is in aws_cost_explorer.py which uses boto3 to fetch
daily costs from AWS Cost Explorer API, validates credentials via STS, and stores
results in the cost_snapshots table using the same pattern as GCP/Azure providers.

This file is kept for import compatibility but does not register any integration.
See aws_cost_explorer.py for the active registration.
"""
