# Cost Ingestion Pipeline Documentation

## Overview

The cost ingestion pipeline allows Heliox to import GPU cost data from various sources into the database. This implementation provides a **mocked ingestion system** that reads from a JSON file and performs idempotent upserts into the `cost_snapshots` table.

---

## Architecture

### Components

1. **Mock Data File** (`backend/app/data/mock_cost_export.json`)
   - Sample AWS cost data for 14 days
   - 2 GPU types (A100, H100)
   - Realistic cost values

2. **Ingestion Service** (`backend/app/services/cost_ingestion.py`)
   - Loads and validates JSON data
   - Normalizes strings (lowercase provider/gpu_type)
   - Performs idempotent upserts
   - Tracks inserted/updated/failed counts

3. **Admin API** (`backend/app/api/routes/admin.py`)
   - POST `/admin/ingest/cost/mock` - Trigger ingestion
   - GET `/admin/health` - Verify admin API health
   - Protected by API key authentication

4. **Security** (`backend/app/core/security.py`)
   - API key authentication for admin endpoints
   - Validates `X-API-Key` header against `ADMIN_API_KEY` env var

---

## Data Flow

```
┌─────────────────────┐
│  Mock JSON File     │
│  (mock_cost_export) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Load & Validate    │
│  (Pydantic schemas) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Normalize Data     │
│  (lowercase strings)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Idempotent Upsert  │
│  (ON CONFLICT DO    │
│   UPDATE)           │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  cost_snapshots     │
│  (PostgreSQL)       │
└─────────────────────┘
```

---

## API Endpoints

### POST /api/v1/admin/ingest/cost/mock

Ingest mock cost data from JSON file.

**Authentication:**
- Requires `X-API-Key` header
- Key must match `ADMIN_API_KEY` environment variable

**Request:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/ingest/cost/mock \
  -H "X-API-Key: your-admin-api-key"
```

**Response (Success):**
```json
{
  "status": "success",
  "message": "Successfully ingested 28 cost records. 28 inserted, 0 updated.",
  "result": {
    "total_records": 28,
    "inserted": 28,
    "updated": 0,
    "failed": 0,
    "errors": []
  }
}
```

**Response (Partial Success):**
```json
{
  "status": "partial_success",
  "message": "Ingested 26 records, 2 failed. Check logs for details.",
  "result": {
    "total_records": 28,
    "inserted": 20,
    "updated": 6,
    "failed": 2,
    "errors": [
      "Record 15: Cost must be positive",
      "Record 23: Invalid date format"
    ]
  }
}
```

**Error Responses:**

```json
// 401 Unauthorized - Missing API key
{
  "detail": "Missing X-API-Key header"
}

// 401 Unauthorized - Invalid API key
{
  "detail": "Invalid API key"
}

// 400 Bad Request - Invalid JSON
{
  "detail": {
    "message": "Invalid cost data format",
    "errors": [
      "cost_data -> 0 -> cost_usd: Input should be greater than 0",
      "cost_data -> 5 -> date: Invalid date format"
    ]
  }
}

// 500 Internal Server Error - Database failure
{
  "detail": "Failed to ingest cost data. Check server logs for details."
}
```

---

### GET /api/v1/admin/health

Verify admin API health and authentication.

**Authentication:**
- Requires `X-API-Key` header

**Request:**
```bash
curl -X GET http://localhost:8000/api/v1/admin/health \
  -H "X-API-Key: your-admin-api-key"
```

**Response:**
```json
{
  "status": "ok",
  "message": "Admin API is healthy and authenticated"
}
```

---

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Admin API Key (change in production!)
ADMIN_API_KEY=heliox-admin-key-change-in-production
```

**⚠️ Security Warning:**
- Change the default API key in production
- Use a strong, randomly generated key
- Keep the key secret and secure
- Rotate keys periodically

**Generate a secure key:**
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Mock Data Format

### JSON Structure

```json
{
  "export_metadata": {
    "generated_at": "2026-01-09T20:00:00Z",
    "source": "aws_cost_explorer_mock",
    "currency": "USD",
    "description": "Mock AWS GPU cost data"
  },
  "cost_data": [
    {
      "date": "2026-01-01",
      "provider": "AWS",
      "gpu_type": "A100",
      "cost_usd": 1245.67
    },
    ...
  ]
}
```

### Field Descriptions

- `date` (string, ISO 8601): Date of cost snapshot
- `provider` (string): Cloud provider name (will be normalized to lowercase)
- `gpu_type` (string): GPU model (will be normalized to lowercase)
- `cost_usd` (number): Cost in USD, must be positive

### Validation Rules

1. **date**: Valid ISO 8601 date format (YYYY-MM-DD)
2. **provider**: 1-100 characters, non-empty
3. **gpu_type**: 1-100 characters, non-empty
4. **cost_usd**: Positive number, rounded to 2 decimal places

---

## Idempotency

The ingestion pipeline is **fully idempotent**:

### Unique Key
Records are identified by: `(date, provider, gpu_type)`

### Behavior

**First Run:**
```json
// Insert 28 new records
{
  "inserted": 28,
  "updated": 0
}
```

**Second Run (same data):**
```json
// Update 28 existing records (only cost_usd changes)
{
  "inserted": 0,
  "updated": 28
}
```

**Mixed Run (some new, some existing):**
```json
// Insert new, update existing
{
  "inserted": 15,
  "updated": 13
}
```

### Database Constraint

```sql
ALTER TABLE cost_snapshots 
ADD CONSTRAINT uq_cost_snapshot_date_provider_gpu 
UNIQUE (date, provider, gpu_type);
```

---

## Data Normalization

All string fields are normalized before insertion:

```python
# Input
{
  "provider": "AWS",
  "gpu_type": "A100"
}

# Stored in database
{
  "provider": "aws",    # lowercase
  "gpu_type": "a100"    # lowercase
}
```

### Why Normalize?

1. **Consistency**: Prevents duplicates from case variations
2. **Querying**: Simplifies filtering and aggregation
3. **Reporting**: Ensures consistent data for analytics

---

## Testing

### Manual Testing

```bash
# 1. Check admin API health
curl -X GET http://localhost:8000/api/v1/admin/health \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Expected: {"status":"ok", ...}

# 2. Run ingestion (first time)
curl -X POST http://localhost:8000/api/v1/admin/ingest/cost/mock \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Expected: 28 inserted, 0 updated

# 3. Run ingestion (second time - idempotency test)
curl -X POST http://localhost:8000/api/v1/admin/ingest/cost/mock \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Expected: 0 inserted, 28 updated

# 4. Verify data in database
docker-compose exec postgres psql -U postgres -d heliox \
  -c "SELECT COUNT(*), SUM(cost_usd) FROM cost_snapshots;"

# Expected: 28 records, total cost ~$52k
```

### Automated Test Script

Run the included test script:
```bash
./test_cost_ingestion.sh
```

---

## Error Handling

### Validation Errors (400)

**Invalid JSON structure:**
- Missing required fields
- Wrong data types
- Out-of-range values

**Action:** Fix the JSON file and retry

### Authentication Errors (401)

**Missing or invalid API key:**
- No `X-API-Key` header
- Wrong API key value

**Action:** Add correct API key header

### Database Errors (500)

**Database connection failure:**
- PostgreSQL unavailable
- Connection timeout

**Action:** Check database health, restart services

**Constraint violation:**
- Unique constraint error (should not happen with ON CONFLICT)

**Action:** Check logs, verify database state

---

## Logging

The ingestion service logs all operations:

### Log Levels

**INFO:**
- Ingestion start/complete
- Record counts (inserted/updated)
- Success messages

**DEBUG:**
- Individual record processing
- Normalization details
- Upsert operations

**ERROR:**
- Validation failures
- Database errors
- Critical exceptions

### View Logs

```bash
# All logs
docker-compose logs api

# Follow logs in real-time
docker-compose logs -f api

# Filter for ingestion logs
docker-compose logs api | grep "cost_ingestion"
```

### Example Log Output

```
INFO: Starting mock cost data ingestion
INFO: Loading cost data from: /app/app/data/mock_cost_export.json
INFO: Successfully loaded 28 cost records
INFO: Starting ingestion of 28 cost records
DEBUG: Record 1/28: inserted 2026-01-01 | aws | a100 | $1245.67
DEBUG: Record 2/28: inserted 2026-01-01 | aws | h100 | $2189.45
...
INFO: Ingestion complete: 28 inserted, 0 updated, 0 failed
```

---

## Production Considerations

### Security

1. **Change default API key**
   ```bash
   ADMIN_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
   ```

2. **Use HTTPS** in production
   - Encrypt API key in transit
   - Prevent man-in-the-middle attacks

3. **Restrict access**
   - Firewall admin endpoints
   - Use IP allowlisting if possible

4. **Audit logging**
   - Log all admin API calls
   - Track who ingested what and when

### Scalability

1. **Batch processing**
   - Current: Processes records sequentially
   - Future: Add batch insert for large datasets

2. **Async processing**
   - Current: Synchronous endpoint
   - Future: Queue-based background processing

3. **Error recovery**
   - Current: Logs errors, continues processing
   - Future: Dead letter queue for failed records

### Monitoring

1. **Ingestion metrics**
   - Track insert/update/failure counts
   - Monitor ingestion duration
   - Alert on high failure rates

2. **Data quality**
   - Validate cost trends
   - Detect anomalies
   - Alert on missing data

---

## Future Enhancements

### Phase 1: Real Cloud Integration
- AWS Cost Explorer API
- GCP Billing API
- Azure Cost Management API

### Phase 2: Advanced Features
- Scheduled automated ingestion
- Cost anomaly detection
- Historical data backfill
- Multi-provider reconciliation

### Phase 3: Analytics
- Cost forecasting
- Budget alerts
- Cost optimization recommendations
- Interactive dashboards

---

## Troubleshooting

### Issue: "Missing X-API-Key header"

**Cause:** API key not provided in request

**Solution:**
```bash
curl -H "X-API-Key: your-key-here" ...
```

### Issue: "Invalid API key"

**Cause:** Wrong API key value

**Solution:** Check `ADMIN_API_KEY` in `.env` file

### Issue: "Cost data file not found"

**Cause:** Mock JSON file missing

**Solution:** Ensure `backend/app/data/mock_cost_export.json` exists

### Issue: "Invalid cost data format"

**Cause:** JSON doesn't match expected schema

**Solution:** Validate JSON against schema, fix errors

### Issue: Ingestion succeeds but no data in DB

**Cause:** Transaction not committed

**Solution:** Check for errors in logs, verify database connection

---

## API Documentation

Interactive API documentation available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Navigate to the "Admin" section to see all admin endpoints.

---

## Summary

✅ **Production-ready mocked cost ingestion pipeline**
✅ **Idempotent upserts** - Safe to run multiple times
✅ **API key authentication** - Secure admin endpoints
✅ **Comprehensive error handling** - Graceful failure modes
✅ **Detailed logging** - Full observability
✅ **Data normalization** - Consistent storage
✅ **Well documented** - Easy to understand and maintain

**Ready for real cloud integration when needed!**

