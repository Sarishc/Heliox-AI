"""Integration providers."""

# Import all providers here to register them
from app.integrations.providers.aws_cost_explorer import (
    AWSCostExplorerIntegration as AWSCostExplorerIntegration,
)
from app.integrations.providers.azure_cost_management import (
    AzureCostManagementIntegration as AzureCostManagementIntegration,
)
from app.integrations.providers.gcp_billing_bigquery import (
    GCPBillingBigQueryIntegration as GCPBillingBigQueryIntegration,
)
