"""Integration providers."""

# Import all providers here to register them
from app.integrations.providers.aws_cost_explorer import AWSCostExplorerIntegration
from app.integrations.providers.gcp_billing_bigquery import GCPBillingBigQueryIntegration

# Future providers:
# from app.integrations.providers.azure import AzureIntegration
