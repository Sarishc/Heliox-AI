# AWS Cost Explorer Integration Guide

Complete guide for connecting AWS Cost Explorer to Heliox for automatic GPU cost ingestion.

---

## Overview

The AWS Cost Explorer integration automatically:
- Pulls daily unblended costs from your AWS account
- Imports GPU and infrastructure costs into Heliox
- Maps costs to teams using AWS cost allocation tags
- Syncs hourly or on-demand

---

## Prerequisites

1. **AWS Account** with Cost Explorer enabled
2. **IAM User** with Cost Explorer permissions (see policy below)
3. **Cost Allocation Tags** (optional but recommended for team mapping)

---

## Step 1: Create IAM User and Access Keys

### 1.1 Create IAM User

```bash
# Via AWS Console:
# 1. Go to IAM > Users > Create user
# 2. Name: heliox-cost-reader
# 3. Select "Programmatic access" (Access key)
# 4. Skip "Add user to group" (we'll attach policy directly)
# 5. Create user

# Via AWS CLI:
aws iam create-user --user-name heliox-cost-reader
```

### 1.2 Attach Least-Privilege IAM Policy

Create a policy with **minimal permissions** for Cost Explorer:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "HelioxCostExplorerReadOnly",
      "Effect": "Allow",
      "Action": [
        "ce:GetCostAndUsage",
        "ce:GetCostForecast",
        "ce:GetDimensionValues",
        "ce:GetTags",
        "sts:GetCallerIdentity"
      ],
      "Resource": "*"
    }
  ]
}
```

**Apply the policy**:

```bash
# Save policy JSON to heliox-cost-policy.json

# Create policy
aws iam create-policy \
  --policy-name HelioxCostExplorerReadOnly \
  --policy-document file://heliox-cost-policy.json

# Attach to user
aws iam attach-user-policy \
  --user-name heliox-cost-reader \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/HelioxCostExplorerReadOnly
```

### 1.3 Generate Access Keys

```bash
aws iam create-access-key --user-name heliox-cost-reader
```

**Output**:
```json
{
  "AccessKey": {
    "AccessKeyId": "AKIA...",
    "SecretAccessKey": "...",
    "Status": "Active"
  }
}
```

**⚠️ Save these credentials securely!** They will be encrypted in Heliox but keep a backup.

---

## Step 2: Enable Cost Allocation Tags (Optional but Recommended)

Cost allocation tags allow Heliox to map AWS costs to specific teams.

### 2.1 Activate Tags in AWS Console

1. Go to **AWS Billing Console** > **Cost Allocation Tags**
2. Find your tag key (e.g., `Team`, `Department`, `Project`)
3. Click **Activate**
4. Wait 24 hours for data to populate

### 2.2 Tag Your Resources

```bash
# Example: Tag EC2 instances with Team
aws ec2 create-tags \
  --resources i-1234567890abcdef0 \
  --tags Key=Team,Value=ml-research

# Example: Tag SageMaker endpoints
aws sagemaker add-tags \
  --resource-arn arn:aws:sagemaker:us-east-1:123456789012:endpoint/my-endpoint \
  --tags Key=Team,Value=data-science
```

### 2.3 Common Tag Keys

| Tag Key | Use Case | Example Values |
|---------|----------|----------------|
| `Team` | Map to Heliox teams | ml-research, data-science, platform |
| `Environment` | Filter by environment | prod, staging, dev |
| `Project` | Track project costs | llm-training, recommendation-engine |
| `CostCenter` | Finance tracking | engineering, research, ops |

---

## Step 3: Connect AWS to Heliox

### 3.1 Via Frontend UI

1. Navigate to **Settings > Integrations** in Heliox dashboard
2. Click **Connect** on AWS Cost Explorer card
3. Fill in the form:

   **Required**:
   - Connection Name: `AWS Production`
   - AWS Access Key ID: `AKIA...` (from Step 1.3)
   - AWS Secret Access Key: `...` (from Step 1.3)
   - AWS Region: `us-east-1` (or your primary region)

   **Optional**:
   - Linked Account IDs: `123456789012, 987654321098` (comma-separated)
   - Cost Allocation Tag Key: `Team` (from Step 2)
   - Cost Allocation Tag Values: `ml-research, data-science` (filter specific teams)
   - Description: `Main AWS account for GPU costs`

4. Click **Test Credentials** (verifies access)
5. Click **Connect & Sync** (saves and triggers initial sync)

### 3.2 Via API

```bash
# Test credentials first
curl -X POST http://localhost:8000/api/v1/integrations/aws/test \
  -H "X-API-Key: your-team-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "aws_access_key_id": "AKIA...",
    "aws_secret_access_key": "...",
    "aws_region": "us-east-1"
  }'

# If valid, connect
curl -X POST http://localhost:8000/api/v1/integrations/aws/connect \
  -H "X-API-Key: your-team-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "AWS Production",
    "description": "Main AWS account",
    "provider": "aws",
    "config": {
      "aws_access_key_id": "AKIA...",
      "aws_secret_access_key": "...",
      "aws_region": "us-east-1",
      "linked_account_ids": ["123456789012"],
      "cost_allocation_tag_key": "Team",
      "cost_allocation_tag_values": ["ml-research", "data-science"]
    },
    "auto_sync_enabled": true,
    "sync_interval_minutes": 60
  }'
```

---

## Step 4: Verify Integration

### 4.1 Check Connection Status

1. Go to **Settings > Integrations**
2. Find your AWS connection
3. Verify status shows **Active** (may take 1-2 minutes for initial sync)

### 4.2 Trigger Manual Sync

Click **Sync Now** button to immediately pull latest costs.

### 4.3 View Imported Costs

1. Go to **Dashboard**
2. Check **Daily Spend Trend** widget
3. Costs should appear with provider = "aws"

### 4.4 Check Sync Logs

```bash
# Backend logs
docker logs heliox-worker --tail 100 | grep "AWS Cost Explorer sync"

# Check sync history
curl http://localhost:8000/api/v1/integrations/{connection_id}/sync-history \
  -H "X-API-Key: your-team-api-key"
```

---

## How It Works

### Data Flow

```
AWS Cost Explorer API
    ↓ (sync every 60 min)
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

2. **Grouping**:
   - By SERVICE (EC2, SageMaker, etc.)
   - By LINKED_ACCOUNT (if multi-account)
   - By TAG (if cost allocation tag configured)

3. **Team Mapping**:
   - If tag value matches team name → assign to that team
   - Otherwise → assign to integration owner team

4. **Idempotency**:
   - Upserts based on (team_id, date, provider, gpu_type)
   - No duplicate costs imported

---

## Team Mapping Examples

### Scenario 1: Single Team (No Tags)

All AWS costs → Integration owner team

### Scenario 2: Multiple Teams with Tag Mapping

**AWS Tags**:
- Instance 1: `Team=ml-research`
- Instance 2: `Team=data-science`
- Instance 3: (no tag)

**Heliox Teams**:
- `ml-research` (exists)
- `data-science` (exists)
- `Demo Team` (integration owner)

**Result**:
- Instance 1 costs → `ml-research` team
- Instance 2 costs → `data-science` team
- Instance 3 costs → `Demo Team` (fallback)

---

## Troubleshooting

### "Invalid AWS credentials"

**Check**:
```bash
# Verify access key
aws sts get-caller-identity \
  --profile heliox  # or pass keys explicitly

# Expected output:
# {
#   "UserId": "AIDA...",
#   "Account": "123456789012",
#   "Arn": "arn:aws:iam::123456789012:user/heliox-cost-reader"
# }
```

**Fix**:
- Verify Access Key ID is correct (starts with AKIA)
- Verify Secret Access Key is correct (40+ characters)
- Check keys haven't expired or been deactivated

### "AccessDenied: User is not authorized to perform ce:GetCostAndUsage"

**Check**:
```bash
# Verify policy is attached
aws iam list-attached-user-policies --user-name heliox-cost-reader
```

**Fix**:
- Attach the HelioxCostExplorerReadOnly policy (see Step 1.2)
- Wait 1-2 minutes for IAM changes to propagate

### "No costs appearing in dashboard"

**Check**:
1. Sync status: Settings > Integrations > Check connection status
2. Sync history: Click connection, view sync runs
3. Logs: `docker logs heliox-worker | grep AWS`

**Common Causes**:
- AWS account has no Cost Explorer data yet (wait 24 hours after enabling)
- Cost allocation tags not activated (takes 24 hours)
- Zero costs in query period (try extending date range)
- Linked account IDs filter too restrictive

### "Sync takes > 2 minutes"

**Normal** for large AWS accounts with:
- 10+ linked accounts
- 100+ services
- 365+ days of data

**Optimization**:
- Limit linked_account_ids to GPU accounts only
- Use shorter sync periods (don't query all historical data)
- Increase Celery worker concurrency

---

## Security Best Practices

### ✅ DO:

1. **Use least-privilege IAM policy** (Cost Explorer read-only)
2. **Rotate access keys every 90 days**
   ```bash
   # Create new key
   aws iam create-access-key --user-name heliox-cost-reader
   
   # Update in Heliox (Edit integration)
   
   # Deactivate old key
   aws iam update-access-key \
     --user-name heliox-cost-reader \
     --access-key-id AKIA_OLD \
     --status Inactive
   
   # Delete old key after verifying new one works
   aws iam delete-access-key \
     --user-name heliox-cost-reader \
     --access-key-id AKIA_OLD
   ```

3. **Enable CloudTrail logging** for IAM user actions
4. **Set up AWS CloudWatch alarms** for unusual API usage
5. **Use IAM role assumption** (advanced - see below)

### ❌ DON'T:

1. ❌ Use root account credentials
2. ❌ Grant `*` permissions
3. ❌ Share credentials via email or Slack
4. ❌ Commit credentials to git
5. ❌ Use the same credentials for production and development

### 🔐 Advanced: IAM Role Assumption (Recommended for Production)

Instead of long-lived access keys, use IAM roles with temporary credentials:

**Step 1**: Create IAM role in AWS account:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::HELIOX_ACCOUNT_ID:user/heliox-service"
    },
    "Action": "sts:AssumeRole"
  }]
}
```

**Step 2**: Update integration to use STS AssumeRole:
```python
# In aws_cost_explorer.py, add support for:
# - role_arn (optional config field)
# - If set, use sts.assume_role() to get temporary credentials
```

**Benefits**:
- Credentials auto-rotate (1-12 hour TTL)
- Can revoke access instantly (detach role)
- Audit trail in CloudTrail

---

## Cost Mapping Details

### Service → GPU Type Mapping

Heliox maps AWS services to GPU types:

| AWS Service | Heliox GPU Type | Notes |
|-------------|-----------------|-------|
| EC2 - Compute | `ec2` | All EC2 instances (simplified) |
| SageMaker | `sagemaker` | SageMaker endpoints and training |
| Other services | `unknown` | Non-GPU services |

**Future Enhancement**: Parse EC2 instance types (p3.2xlarge → V100, p4d.24xlarge → A100) from detailed billing or resource tags.

### Tag-Based Team Mapping

**Example**: Tag key = `Team`

**AWS Resources**:
```
Instance i-123: Team=ml-research
Instance i-456: Team=data-science
Instance i-789: (no Team tag)
```

**Heliox Teams**:
```
- ml-research (ID: uuid-1)
- data-science (ID: uuid-2)
- Demo Team (ID: uuid-3, integration owner)
```

**Cost Assignment**:
```
i-123 costs → ml-research team (uuid-1)
i-456 costs → data-science team (uuid-2)
i-789 costs → Demo Team (uuid-3, fallback)
```

**Mapping Algorithm**:
1. If tag value exists, find Heliox team where `name ILIKE '%{tag_value}%'`
2. If found, assign cost to that team
3. Otherwise, assign to integration owner team (fallback)

---

## Sync Behavior

### Initial Sync
- Pulls last 30 days of cost data
- Creates cost_snapshots records
- Status: "pending" → "active" on success

### Incremental Syncs
- Pulls costs since last successful sync
- Upserts existing records (aggregates if multiple services)
- Runs automatically every 60 minutes (configurable)

### Manual Syncs
- Click "Sync Now" in UI or call POST `/integrations/{id}/sync`
- Immediate sync (doesn't wait for scheduled interval)

### Sync Failures
- Status: "active" → "error"
- Last error displayed in UI
- Retries: 3 automatic retries (Celery config)
- Manual retry: Click "Sync Now"

---

## API Reference

### Test Credentials
```bash
POST /api/v1/integrations/aws/test
{
  "aws_access_key_id": "AKIA...",
  "aws_secret_access_key": "...",
  "aws_region": "us-east-1"
}

# Response (valid):
{
  "valid": true,
  "account_id": "123456789012",
  "caller_arn": "arn:aws:iam::123456789012:user/heliox-cost-reader",
  "message": "AWS Cost Explorer connection successful",
  "details": {
    "api_reachable": true,
    "credentials_valid": true,
    "cost_explorer_access": true
  }
}

# Response (invalid):
{
  "valid": false,
  "message": "Invalid AWS credentials or insufficient permissions",
  "details": {
    "error_code": "InvalidClientTokenId"
  }
}
```

### Connect AWS
```bash
POST /api/v1/integrations/aws/connect
{
  "name": "AWS Production",
  "description": "Main AWS account",
  "provider": "aws",
  "config": {
    "aws_access_key_id": "AKIA...",
    "aws_secret_access_key": "...",
    "aws_region": "us-east-1",
    "linked_account_ids": ["123456789012"],
    "cost_allocation_tag_key": "Team",
    "cost_allocation_tag_values": ["ml-research", "data-science"]
  },
  "auto_sync_enabled": true,
  "sync_interval_minutes": 60
}

# Response:
{
  "id": "uuid",
  "status": "pending",
  "config": {
    "aws_access_key_id": "***REDACTED***",
    "aws_secret_access_key": "***REDACTED***",
    "aws_region": "us-east-1"
  },
  "last_sync_at": null,
  ...
}
```

### Trigger Sync
```bash
POST /api/v1/integrations/{connection_id}/sync

# Response:
{
  "id": "sync-run-uuid",
  "status": "running",
  "started_at": "2026-01-27T17:00:00Z"
}
```

### Check Sync History
```bash
GET /api/v1/integrations/{connection_id}/sync-history?limit=10

# Response:
[
  {
    "id": "uuid",
    "started_at": "2026-01-27T17:00:00Z",
    "finished_at": "2026-01-27T17:01:23Z",
    "status": "success",
    "metrics": {
      "records_fetched": 150,
      "records_saved": 145,
      "records_skipped": 5,
      "date_range": {"start": "2025-12-28", "end": "2026-01-27"}
    }
  }
]
```

---

## Monitoring

### Sync Success Rate
```bash
# Check sync run statuses
docker-compose exec postgres psql -U postgres -d heliox -c \
  "SELECT status, COUNT(*) FROM integration_sync_runs WHERE connection_id = 'your-connection-id' GROUP BY status;"

# Expected:
#   status  | count
# ----------+-------
#  success  |   142
#  failed   |     3
```

### Cost Data Completeness
```bash
# Check imported cost snapshots
docker-compose exec postgres psql -U postgres -d heliox -c \
  "SELECT date, SUM(cost_usd) FROM cost_snapshots WHERE provider = 'aws' GROUP BY date ORDER BY date DESC LIMIT 7;"

# Verify costs match AWS Billing Dashboard
```

### Logs
```bash
# Integration sync logs
docker logs heliox-worker --tail 100 | grep "AWS Cost Explorer"

# API logs
docker logs heliox-api --tail 100 | grep integrations
```

---

## Performance & Costs

### AWS Cost Explorer API Limits
- **Free tier**: First 1,000 GetCostAndUsage requests per month
- **Paid tier**: $0.01 per request after free tier
- **Rate limit**: 400 requests per second (unlikely to hit)

### Heliox Sync Costs
- **Hourly sync** (default): ~720 requests/month = **Free**
- **Every 30 min**: ~1,440 requests/month = **~$5/month**
- **Every 5 min**: ~8,640 requests/month = **~$75/month**

**Recommendation**: Hourly sync is sufficient for most use cases.

### Sync Performance
- **Small account** (1-5 services): < 10 seconds
- **Medium account** (10-20 services, 5 linked accounts): 30-60 seconds
- **Large account** (50+ services, 20+ linked accounts): 1-2 minutes

---

## FAQ

### Q: Does this sync historical data?
**A**: Yes, initial sync pulls last 30 days. Use API to manually trigger longer historical syncs if needed.

### Q: Can I sync multiple AWS accounts?
**A**: Yes! Either:
1. Use Organization management account with access to all member accounts
2. Create separate integrations per account

### Q: What if I have multiple regions?
**A**: Cost Explorer aggregates all regions by default. The `aws_region` config only sets which regional API endpoint to use.

### Q: How often should I sync?
**A**: 
- **Hourly** (60 min): Good for most use cases, stays in free tier
- **Every 30 min**: For faster cost visibility
- **Daily**: Sufficient if you only review costs once per day

### Q: Can I exclude certain services?
**A**: Not directly. Filter in Heliox dashboard by gpu_type or use linked_account_ids to exclude entire accounts.

### Q: What data is stored?
**A**: Only:
- Date
- Service name (as gpu_type)
- Account ID (in linked_account_ids)
- Cost (unblended)
- Team assignment

**Not stored**: Resource IDs, instance types, tags (beyond mapping)

---

## Next Steps

### After Connecting AWS:

1. **Wait 2-5 minutes** for initial sync to complete
2. **Check dashboard** for imported costs
3. **Configure budgets** based on AWS spend
4. **Set up alerts** for cost anomalies
5. **Tag more resources** for better team attribution

### Enhance Your Setup:

1. **Enable AWS Cost Anomaly Detection** (free) in AWS Console
2. **Set up AWS Budgets** for backup alerting
3. **Create CloudWatch dashboard** for AWS API usage monitoring
4. **Implement Reserved Instance** recommendations (future Heliox feature)

---

## Support

- **Documentation**: `/backend/app/integrations/README.md`
- **API Docs**: `http://localhost:8000/docs#/Integrations`
- **Logs**: `docker logs heliox-worker | grep AWS`
- **Issues**: Check sync history and connection status in UI

---

*End of AWS Integration Guide*
