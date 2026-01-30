# Heliox Integrations Module

This module provides a foundation for connecting external services to Heliox to automatically sync GPU costs, usage data, and other metrics.

## Architecture

```
integrations/
├── __init__.py                 # Module exports
├── base.py                     # IntegrationBase abstract class
├── registry.py                 # Integration registry
├── models.py                   # Database models
├── encryption.py               # Config encryption utilities
├── providers/                  # Integration implementations
│   ├── __init__.py
│   └── aws.py                  # AWS Cost Explorer (example)
└── README.md                   # This file
```

## How It Works

### 1. Integration Registration

Integrations inherit from `IntegrationBase` and register themselves with the global `integration_registry`:

```python
from app.integrations.base import IntegrationBase, IntegrationProvider
from app.integrations.registry import integration_registry

class AWSIntegration(IntegrationBase):
    provider = IntegrationProvider.AWS
    display_name = "AWS Cost Explorer"
    # ... implementation ...

# Register
integration_registry.register(IntegrationProvider.AWS, AWSIntegration)
```

### 2. Configuration Storage

Integration configurations (API keys, credentials, etc.) are:
- Encrypted using Fernet (symmetric encryption)
- Stored in the `integration_connections` table
- Never logged or exposed in API responses (masked with `get_display_config()`)

### 3. Data Synchronization

Syncs are triggered:
- **Manually** via POST `/api/v1/integrations/{id}/sync`
- **Automatically** via Celery Beat (every 5 minutes for enabled connections)

Each sync creates an `IntegrationSyncRun` record for auditing.

### 4. Health Checks

Health checks verify:
- External service is reachable
- Credentials are valid
- API rate limits (if applicable)

## Database Schema

### `integration_connections`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| team_id | UUID | Team owner (FK to teams) |
| provider | Enum | Integration provider (aws, gcp, etc.) |
| name | String | User-friendly name |
| description | Text | Optional description |
| config_encrypted | Text | Encrypted JSON configuration |
| status | Enum | active, error, disabled, pending |
| last_error | Text | Last error message |
| last_sync_at | Timestamp | Last sync attempt |
| last_successful_sync_at | Timestamp | Last successful sync |
| auto_sync_enabled | Boolean | Enable automatic syncing |
| sync_interval_minutes | Integer | Sync frequency (default: 60) |

### `integration_sync_runs`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| connection_id | UUID | FK to integration_connections |
| started_at | Timestamp | When sync started |
| finished_at | Timestamp | When sync completed |
| status | Enum | running, success, failed, partial |
| error | Text | Error message if failed |
| error_details | JSON | Detailed error context |
| metrics_json | JSON | Sync metrics (records fetched, saved, etc.) |
| triggered_by | String | manual, scheduled, webhook |

## API Endpoints

### List Available Integrations
```
GET /api/v1/integrations/available
```
Returns all available integrations (enabled and disabled).

### Create Connection
```
POST /api/v1/integrations/connect
{
  "provider": "aws",
  "name": "AWS Production",
  "config": {
    "aws_access_key_id": "...",
    "aws_secret_access_key": "...",
    "aws_region": "us-east-1"
  },
  "auto_sync_enabled": true,
  "sync_interval_minutes": 60
}
```

### List Connections
```
GET /api/v1/integrations
```
Returns all connections for the authenticated team.

### Trigger Sync
```
POST /api/v1/integrations/{id}/sync
```
Manually trigger a sync for a connection.

### Check Health
```
GET /api/v1/integrations/{id}/health
```
Check integration health (tests connectivity and credentials).

### Get Sync History
```
GET /api/v1/integrations/{id}/sync-history?limit=10
```
Get recent sync runs for a connection.

### Delete Connection
```
DELETE /api/v1/integrations/{id}
```
Delete a connection (cascades to sync runs).

## Adding a New Integration

### Step 1: Define the Provider

Add to `IntegrationProvider` enum in `base.py`:

```python
class IntegrationProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    YOUR_PROVIDER = "your_provider"  # Add here
```

### Step 2: Implement Integration Class

Create `providers/your_provider.py`:

```python
from app.integrations.base import IntegrationBase, IntegrationProvider
from app.integrations.registry import integration_registry

class YourProviderIntegration(IntegrationBase):
    provider = IntegrationProvider.YOUR_PROVIDER
    display_name = "Your Provider Name"
    description = "Brief description of what this syncs"
    
    required_config_fields = ["api_key", "endpoint"]
    optional_config_fields = ["region"]
    
    def validate_config(self, config):
        """Validate configuration (don't log secrets!)"""
        if not config.get("api_key"):
            raise ValueError("api_key is required")
        if not config.get("endpoint").startswith("https://"):
            raise ValueError("endpoint must use HTTPS")
    
    async def sync(self, team_id, last_sync_at=None):
        """Fetch and save data"""
        # 1. Connect to external API
        # 2. Fetch data since last_sync_at
        # 3. Transform to Heliox format
        # 4. Save to database
        # 5. Return metrics
        return {
            "records_fetched": 100,
            "records_saved": 95,
            "records_skipped": 5,
            "errors": []
        }
    
    async def health(self):
        """Check integration health"""
        # Test API connectivity
        return {
            "status": "healthy",
            "message": "All systems operational",
            "details": {
                "api_reachable": True,
                "credentials_valid": True
            }
        }

# Register
integration_registry.register(IntegrationProvider.YOUR_PROVIDER, YourProviderIntegration)
```

### Step 3: Import Provider

Add to `providers/__init__.py`:

```python
from app.integrations.providers.your_provider import YourProviderIntegration
```

### Step 4: Test

1. Start Heliox backend
2. Check `/api/v1/integrations/available` - your provider should appear
3. Create a connection via API or frontend
4. Trigger a sync and verify data is imported

## Security Best Practices

### DO:
- ✅ Encrypt all sensitive configuration with Fernet
- ✅ Use `get_display_config()` to mask secrets in API responses
- ✅ Validate configuration in `validate_config()`
- ✅ Use constant-time comparison for API keys
- ✅ Log only non-sensitive information
- ✅ Rotate encryption keys periodically

### DON'T:
- ❌ Log decrypted configuration
- ❌ Return decrypted secrets in API responses
- ❌ Store credentials in plaintext
- ❌ Skip validation of external API certificates
- ❌ Hardcode encryption keys

## Environment Variables

### Required (Production)

```bash
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
INTEGRATIONS_ENCRYPTION_KEY=<your_key_here>
```

### Optional (Development)

If `INTEGRATIONS_ENCRYPTION_KEY` is not set in development, a temporary key will be generated. **This is NOT safe for production.**

## Testing

### Unit Tests

```python
def test_integration_validates_config():
    integration = YourProviderIntegration({"api_key": "test"})
    integration.validate_config({"api_key": "test", "endpoint": "https://api.example.com"})

def test_integration_rejects_invalid_config():
    with pytest.raises(ValueError):
        integration = YourProviderIntegration({"api_key": "test"})
        integration.validate_config({})  # Missing required field
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_sync_imports_data():
    integration = YourProviderIntegration({
        "api_key": "test_key",
        "endpoint": "https://api.example.com"
    })
    
    metrics = await integration.sync(team_id="test-team-id")
    
    assert metrics["records_fetched"] > 0
    assert metrics["records_saved"] > 0
```

## Celery Tasks

### Manual Sync
Triggered via API endpoint, runs in background.

### Scheduled Sync
Runs every 5 minutes (configurable in `celery_app.py`), checks all connections and syncs those that are due based on `sync_interval_minutes`.

## Monitoring

### Logs
- Integration syncs log to `app.tasks.integration_tasks`
- Check logs for sync failures: `docker logs heliox-worker --tail 100 | grep integration`

### Metrics
Each sync run records metrics in `metrics_json`:
```json
{
  "records_fetched": 100,
  "records_saved": 95,
  "records_skipped": 5,
  "errors": ["minor error 1"],
  "duration_seconds": 12.5
}
```

### Alerts
Set up alerts for:
- Consecutive sync failures (3+)
- Sync duration > 5 minutes
- Error rate > 10%

## Troubleshooting

### "Integration provider not available"
- Check that provider is registered in `integration_registry`
- Verify provider is imported in `providers/__init__.py`

### "Failed to decrypt integration configuration"
- Encryption key may have changed
- Check `INTEGRATIONS_ENCRYPTION_KEY` environment variable
- Re-create connection with new key

### Sync stuck in "running" state
- Check Celery worker logs: `docker logs heliox-worker`
- Restart worker: `docker-compose restart worker`
- Check sync run error in database

### "API key authentication failed"
- Credentials may have expired
- Edit connection and update credentials
- Check provider's API key management

## Examples

### AWS Cost Explorer
See `providers/aws.py` for a template showing:
- Configuration validation
- Health checks
- Sync implementation structure

### Adding Your Own
Copy `providers/aws.py` and modify:
1. Change `provider` and metadata
2. Update `required_config_fields`
3. Implement `validate_config()`
4. Implement `sync()` to fetch and save data
5. Implement `health()` to test connectivity
6. Register in `providers/__init__.py`

## Future Enhancements

- [ ] Webhook support for real-time syncs
- [ ] Sync conflict resolution
- [ ] Data transformation pipelines
- [ ] Integration marketplace
- [ ] OAuth2 flow for user-authorized integrations
- [ ] Bulk import from CSV/JSON
- [ ] Data validation and quality checks
- [ ] Sync scheduling per-connection (custom cron)

## Support

For questions or issues:
- Check logs: `docker logs heliox-worker`
- Review sync history: GET `/api/v1/integrations/{id}/sync-history`
- Test health: GET `/api/v1/integrations/{id}/health`
- See main documentation: `/docs/QUICKSTART.md`
