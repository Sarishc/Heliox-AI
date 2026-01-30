# GCP BigQuery Billing Integration Guide

Complete guide for connecting GCP BigQuery billing export to Heliox for automatic GPU cost ingestion.

---

## Overview

The GCP BigQuery billing integration automatically:
- Pulls daily costs from BigQuery billing export
- Imports GPU and infrastructure costs into Heliox
- Maps costs to teams using GCP labels
- Syncs hourly or on-demand

---

## Prerequisites

1. **GCP Project** with billing enabled
2. **BigQuery Billing Export** configured
3. **Service Account** with BigQuery permissions
4. **GCP Labels** (optional but recommended for team mapping)

---

## Step 1: Enable BigQuery Billing Export

### 1.1 Enable Billing Export in GCP Console

```bash
# Via GCP Console:
# 1. Go to Billing > Billing Export
# 2. Click "Edit Settings" under "BigQuery Export"
# 3. Select or create a BigQuery dataset (e.g., "billing_export")
# 4. Check "Enable BigQuery Export"
# 5. Choose "Standard usage cost data" or "Detailed usage cost data"
# 6. Click "Save"

# Via gcloud CLI:
gcloud beta billing accounts describe BILLING_ACCOUNT_ID

# Create BigQuery dataset
bq mk --dataset --location=US my-project:billing_export

# Enable billing export (must be done via Console currently)
```

### 1.2 Verify Export Table Created

After enabling (wait 24 hours for first data):

```bash
# List tables in billing export dataset
bq ls my-project:billing_export

# Expected table names:
# - gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX (standard)
# - gcp_billing_export_resource_v1_XXXXXX_XXXXXX_XXXXXX (detailed)

# Check table schema
bq show --schema my-project:billing_export.gcp_billing_export_v1_XXXXXX_XXXXXX_XXXXXX

# Query sample data
bq query --use_legacy_sql=false '
  SELECT
    DATE(usage_start_time) as date,
    service.description as service,
    SUM(cost) as total_cost
  FROM `my-project.billing_export.gcp_billing_export_v1_*`
  WHERE DATE(usage_start_time) >= CURRENT_DATE() - 7
  GROUP BY date, service
  ORDER BY date DESC
  LIMIT 10
'
```

---

## Step 2: Create Service Account with BigQuery Permissions

### 2.1 Create Service Account

```bash
# Create service account
gcloud iam service-accounts create heliox-billing-reader \
  --description="Heliox billing data reader" \
  --display-name="Heliox Billing Reader"

# Verify creation
gcloud iam service-accounts list
```

### 2.2 Grant Required IAM Roles

The service account needs **read-only** access to BigQuery:

```bash
# Role 1: BigQuery Data Viewer (read tables)
gcloud projects add-iam-policy-binding MY_PROJECT_ID \
  --member="serviceAccount:heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

# Role 2: BigQuery Job User (run queries)
gcloud projects add-iam-policy-binding MY_PROJECT_ID \
  --member="serviceAccount:heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Verify roles
gcloud projects get-iam-policy MY_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:heliox-billing-reader"
```

**Minimum Required Roles**:
- `roles/bigquery.dataViewer` - Read BigQuery datasets and tables
- `roles/bigquery.jobUser` - Execute BigQuery queries

**Alternative (More Restrictive)**:

If you want dataset-level permissions only (not project-level):

```bash
# Grant access to specific dataset only
bq show --format=prettyjson my-project:billing_export > dataset.json

# Add service account to dataset ACL
bq update --source dataset.json \
  --add_iam_policy_member \
  serviceAccount:heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com:roles/bigquery.dataViewer \
  my-project:billing_export
```

### 2.3 Generate Service Account JSON Key

```bash
# Create and download JSON key
gcloud iam service-accounts keys create heliox-sa-key.json \
  --iam-account=heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com

# Output: heliox-sa-key.json created

# ⚠️ KEEP THIS FILE SECURE! It contains private keys.
```

**JSON Key Contents**:
```json
{
  "type": "service_account",
  "project_id": "my-project-123",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "heliox-billing-reader@my-project-123.iam.gserviceaccount.com",
  "client_id": "1234567890",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

---

## Step 3: Enable GCP Labels for Team Mapping (Optional but Recommended)

GCP labels allow Heliox to map costs to specific teams.

### 3.1 Add Labels to Resources

```bash
# Example: Label a Compute Engine instance
gcloud compute instances add-labels my-gpu-vm \
  --labels=team=ml-research,environment=prod

# Example: Label a GKE cluster
gcloud container clusters update my-gke-cluster \
  --update-labels team=data-science

# Example: Label a Vertex AI endpoint
gcloud ai endpoints update ENDPOINT_ID \
  --region=us-central1 \
  --update-labels team=ml-research
```

### 3.2 Common Label Keys

| Label Key | Use Case | Example Values |
|-----------|----------|----------------|
| `team` | Map to Heliox teams | ml-research, data-science, platform |
| `environment` | Filter by environment | prod, staging, dev |
| `project` | Track project costs | llm-training, recommendation-engine |
| `cost-center` | Finance tracking | engineering, research, ops |

### 3.3 Label Best Practices

1. **Use lowercase** and hyphens (not underscores or spaces)
2. **Be consistent** across all resources
3. **Label at creation time** (labels don't affect historical costs)
4. **Audit regularly** using GCP Asset Inventory

```bash
# Find unlabeled resources
gcloud asset search-all-resources \
  --scope=projects/MY_PROJECT_ID \
  --query="labels:*" \
  --format="table(name, labels)"
```

---

## Step 4: Connect GCP to Heliox

### 4.1 Via Frontend UI

1. Navigate to **Settings > Integrations** in Heliox dashboard
2. Click **Connect** on GCP BigQuery Billing card
3. Fill in the form:

   **Required**:
   - Connection Name: `GCP Production`
   - GCP Project ID: `my-project-123`
   - BigQuery Dataset: `billing_export`
   - Billing Export Table: `gcp_billing_export_v1_XXXXXX` (your table name)
   - Service Account JSON: (paste entire JSON key from Step 2.3)

   **Optional**:
   - Label Key for Team: `team` (from Step 3)
   - Description: `Main GCP billing export`

4. Click **Test Credentials** (verifies access)
5. Click **Connect & Sync** (saves and triggers initial sync)

### 4.2 Via API

```bash
# Read service account JSON
SA_JSON=$(cat heliox-sa-key.json | jq -c .)

# Test credentials first
curl -X POST http://localhost:8000/api/v1/integrations/gcp/test \
  -H "X-API-Key: your-team-api-key" \
  -H "Content-Type: application/json" \
  -d "{
    \"gcp_project_id\": \"my-project-123\",
    \"bigquery_dataset\": \"billing_export\",
    \"billing_export_table\": \"gcp_billing_export_v1_XXXXXX\",
    \"service_account_json\": $SA_JSON
  }"

# If valid, connect
curl -X POST http://localhost:8000/api/v1/integrations/gcp/connect \
  -H "X-API-Key: your-team-api-key" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"GCP Production\",
    \"description\": \"Main GCP billing export\",
    \"provider\": \"gcp_billing_bigquery\",
    \"config\": {
      \"gcp_project_id\": \"my-project-123\",
      \"bigquery_dataset\": \"billing_export\",
      \"billing_export_table\": \"gcp_billing_export_v1_XXXXXX\",
      \"service_account_json\": $SA_JSON,
      \"label_key_for_team\": \"team\"
    },
    \"auto_sync_enabled\": true,
    \"sync_interval_minutes\": 60
  }"
```

---

## Step 5: Verify Integration

### 5.1 Check Connection Status

1. Go to **Settings > Integrations**
2. Find your GCP connection
3. Verify status shows **Active** (may take 1-2 minutes for initial sync)

### 5.2 Trigger Manual Sync

Click **Sync Now** button to immediately pull latest costs.

### 5.3 View Imported Costs

1. Go to **Dashboard**
2. Check **Daily Spend Trend** widget
3. Costs should appear with provider = "gcp"

### 5.4 Check Sync Logs

```bash
# Backend logs
docker logs heliox-worker --tail 100 | grep "GCP BigQuery billing sync"

# Check sync history
curl http://localhost:8000/api/v1/integrations/{connection_id}/sync-history \
  -H "X-API-Key: your-team-api-key"
```

---

## How It Works

### Data Flow

```
BigQuery Billing Export
    ↓ (query daily costs)
Heliox Integration Worker
    ↓ (transform & map teams)
cost_snapshots table
    ↓ (query)
Analytics Dashboard
```

### Sync Logic

1. **Query Period**:
   - Initial sync: Last 30 days
   - Incremental: Since last successful sync

2. **BigQuery SQL Query**:
```sql
SELECT
  DATE(usage_start_time) as usage_date,
  service.description as service_name,
  project.id as project_id,
  (SELECT value FROM UNNEST(labels) WHERE key = 'team') as team_label,
  SUM(cost) as total_cost
FROM `my-project.billing_export.gcp_billing_export_v1_*`
WHERE DATE(usage_start_time) >= '2026-01-01'
  AND DATE(usage_start_time) < '2026-01-30'
  AND cost > 0
GROUP BY usage_date, service_name, project_id, team_label
ORDER BY usage_date DESC
```

3. **Team Mapping**:
   - If label value matches team name → assign to that team
   - Otherwise → assign to integration owner team

4. **Idempotency**:
   - Upserts based on (team_id, date, provider, gpu_type)
   - No duplicate costs imported

---

## Team Mapping Examples

### Scenario 1: Single Team (No Labels)

All GCP costs → Integration owner team

### Scenario 2: Multiple Teams with Label Mapping

**GCP Labels**:
- VM instance-1: `team=ml-research`
- VM instance-2: `team=data-science`
- VM instance-3: (no label)

**Heliox Teams**:
- `ml-research` (exists)
- `data-science` (exists)
- `Demo Team` (integration owner)

**Result**:
- instance-1 costs → `ml-research` team
- instance-2 costs → `data-science` team
- instance-3 costs → `Demo Team` (fallback)

---

## Troubleshooting

### "Permission denied: BigQuery dataset not found"

**Check**:
```bash
# Verify dataset exists
bq ls my-project:billing_export

# Verify service account has access
gcloud projects get-iam-policy MY_PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:heliox-billing-reader"
```

**Fix**:
- Grant `roles/bigquery.dataViewer` to service account
- Wait 1-2 minutes for IAM changes to propagate

### "Billing export table not found"

**Check**:
```bash
# List tables in dataset
bq ls my-project:billing_export

# Check if export is enabled
# GCP Console > Billing > Billing Export
```

**Common Causes**:
- BigQuery export not enabled (enable in Console)
- No billing data yet (wait 24 hours after enabling)
- Wrong table name (use auto-suggest in Heliox form)

### "No costs appearing in dashboard"

**Check**:
1. Sync status: Settings > Integrations > Check connection status
2. Sync history: Click connection, view sync runs
3. BigQuery data: Run query directly in BigQuery console

**Common Causes**:
- No billing data in BigQuery (wait 24 hours)
- Zero costs in query period (check date range)
- Labels not in billing export (only works with labeled resources)

### "Invalid service account JSON"

**Check**:
- JSON is well-formed (use `jq` to validate)
- All required fields present (type, project_id, private_key, client_email)
- No extra whitespace or newlines

```bash
# Validate JSON
cat heliox-sa-key.json | jq .

# Check required fields
cat heliox-sa-key.json | jq '{type, project_id, client_email}'
```

---

## Security Best Practices

### ✅ DO:

1. **Use least-privilege IAM roles** (BigQuery read-only)
2. **Rotate service account keys every 90 days**
   ```bash
   # Create new key
   gcloud iam service-accounts keys create new-key.json \
     --iam-account=heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com
   
   # Update in Heliox (Edit integration)
   
   # Delete old key
   gcloud iam service-accounts keys delete OLD_KEY_ID \
     --iam-account=heliox-billing-reader@MY_PROJECT_ID.iam.gserviceaccount.com
   ```

3. **Enable Cloud Audit Logs** for BigQuery
4. **Use Workload Identity** for GKE deployments (avoids JSON keys)
5. **Store JSON keys encrypted** (Heliox does this automatically)

### ❌ DON'T:

1. ❌ Grant `roles/owner` or `roles/editor`
2. ❌ Use user credentials (only service accounts)
3. ❌ Share service account keys via email or Slack
4. ❌ Commit keys to git
5. ❌ Use same key for production and development

---

## Cost Mapping Details

### Service → GPU Type Mapping

Heliox maps GCP services to GPU types:

| GCP Service | Heliox GPU Type | Notes |
|-------------|-----------------|-------|
| Compute Engine | `compute-engine` | All VM instances (simplified) |
| Vertex AI / AI Platform | `vertex-ai` | ML training and endpoints |
| GKE / Kubernetes Engine | `gke` | Kubernetes clusters |
| Other services | `unknown` | Non-GPU services |

**Future Enhancement**: Parse machine types (n1-standard-8, a2-highgpu-1g) from detailed billing export.

---

## Performance Characteristics

### Sync Performance:

| Billing Volume | Sync Time | BigQuery Queries | Cost |
|----------------|-----------|------------------|------|
| Small (< 1K rows/day) | 10-20 sec | 1 | Free |
| Medium (1K-10K rows/day) | 30-60 sec | 1 | Free |
| Large (> 10K rows/day) | 1-3 min | 1-2 | Free |

### BigQuery Costs:
- **Free tier**: 1 TB queries/month
- Typical Heliox query: 10-100 MB scanned
- Hourly sync: ~720 queries/month = **Free** (under 1 TB)
- Paid tier: $5 per TB after free tier

### Database Impact:
- **Records per sync**: 10-1000 cost_snapshots
- **Storage**: ~1KB per cost_snapshot
- **Annual growth**: ~365KB per service per project

---

## API Reference

### Test Credentials
```bash
POST /api/v1/integrations/gcp/test
{
  "gcp_project_id": "my-project-123",
  "bigquery_dataset": "billing_export",
  "billing_export_table": "gcp_billing_export_v1_XXXXXX",
  "service_account_json": {...}
}

# Response (valid):
{
  "valid": true,
  "project_id": "my-project-123",
  "dataset": "billing_export",
  "table": "gcp_billing_export_v1_XXXXXX",
  "table_rows": 12345,
  "service_account": "heliox-billing-reader@my-project-123.iam.gserviceaccount.com",
  "message": "GCP BigQuery billing connection successful"
}
```

### Connect GCP
```bash
POST /api/v1/integrations/gcp/connect
{
  "name": "GCP Production",
  "description": "Main GCP billing export",
  "provider": "gcp_billing_bigquery",
  "config": {
    "gcp_project_id": "my-project-123",
    "bigquery_dataset": "billing_export",
    "billing_export_table": "gcp_billing_export_v1_XXXXXX",
    "service_account_json": {...},
    "label_key_for_team": "team"
  },
  "auto_sync_enabled": true,
  "sync_interval_minutes": 60
}

# Response:
{
  "id": "uuid",
  "status": "pending",
  "config": {
    "gcp_project_id": "my-project-123",
    "service_account_json": "***REDACTED***"
  }
}
```

---

## FAQ

### Q: Does this sync historical data?
**A**: Yes, initial sync pulls last 30 days. BigQuery billing export typically has data going back to when you enabled it.

### Q: Can I sync multiple GCP projects?
**A**: Yes! Either:
1. Use multi-project billing export (single dataset)
2. Create separate integrations per project

### Q: What if I have multiple billing accounts?
**A**: Create separate integrations for each billing account's export.

### Q: How often should I sync?
**A**: 
- **Hourly** (60 min): Good for most use cases, minimal BigQuery costs
- **Every 30 min**: For faster cost visibility
- **Daily**: Sufficient if you only review costs once per day

### Q: What data is stored?
**A**: Only:
- Date
- Service name
- Project ID
- Cost (USD)
- Team assignment (via labels)

**Not stored**: Resource IDs, usage amounts, SKU details

---

## Next Steps

### After Connecting GCP:

1. **Wait 1-2 minutes** for initial sync to complete
2. **Check dashboard** for imported costs
3. **Label more resources** for better team attribution
4. **Configure budgets** based on GCP spend
5. **Set up alerts** for cost anomalies

### Enhance Your Setup:

1. **Use detailed billing export** for resource-level costs
2. **Enable BigQuery reservations** for predictable query costs
3. **Set up GCP cost anomaly detection**
4. **Create BigQuery views** for custom cost analysis

---

*End of GCP Integration Guide*
