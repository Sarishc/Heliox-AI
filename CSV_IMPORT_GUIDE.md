# CSV Cost Import Guide

**Date:** 2026-01-11  
**Feature:** Admin-only CSV import for GPU cost data  
**Security:** Protected by admin API key authentication

---

## Overview

The CSV import endpoint allows admin users to upload GPU cost data from CSV files. This feature is designed for early customer onboarding and private beta use.

**Endpoint:** `POST /api/v1/admin/import/cost/csv`

**Security:**
- ✅ Admin-only (requires `X-API-Key` header)
- ✅ Private beta safe (not exposed publicly)
- ✅ File size limit: 10MB
- ✅ Validates all data before import

---

## CSV Format

### Required Header Row
```
date,provider,gpu_type,cost_usd
```

### Data Rows
Each data row must contain exactly 4 columns in this order:

1. **date** (YYYY-MM-DD format)
2. **provider** (string, e.g., "AWS", "GCP", "Azure")
3. **gpu_type** (string, e.g., "A100", "H100", "V100")
4. **cost_usd** (positive decimal number)

### Example CSV

```csv
date,provider,gpu_type,cost_usd
2024-01-01,AWS,A100,1245.67
2024-01-01,AWS,H100,2189.45
2024-01-01,GCP,A100,1150.00
2024-01-02,AWS,A100,1198.32
2024-01-02,AWS,H100,2345.78
2024-01-02,GCP,A100,1120.50
```

### Sample File

A sample CSV file is available at: `backend/app/data/sample_cost_import.csv`

---

## API Usage

### Request

**Method:** `POST`  
**URL:** `https://<backend-url>/api/v1/admin/import/cost/csv`  
**Headers:**
```
X-API-Key: <ADMIN_API_KEY>
Content-Type: multipart/form-data
```

**Body:** Form data with file upload
- Field name: `file`
- File type: `.csv`
- Encoding: UTF-8

### Response (Success)

**Status Code:** `200 OK`

**Response Body:**
```json
{
  "status": "success",
  "message": "Successfully imported 150 records: 120 inserted, 30 updated",
  "result": {
    "total_records": 150,
    "inserted": 120,
    "updated": 30,
    "failed": 0,
    "errors": []
  }
}
```

### Response (Partial Success)

**Status Code:** `200 OK`

**Response Body:**
```json
{
  "status": "partial_success",
  "message": "Import completed with 3 error(s): 147 inserted, 0 updated, 3 failed",
  "result": {
    "total_records": 150,
    "inserted": 147,
    "updated": 0,
    "failed": 3,
    "errors": [
      "Row 45: Invalid date format '2024-13-01'. Expected YYYY-MM-DD",
      "Row 89: cost_usd must be positive, got -100.00",
      "Row 120: Missing provider field"
    ]
  }
}
```

### Response (Validation Error)

**Status Code:** `400 Bad Request`

**Response Body:**
```json
{
  "detail": "CSV validation failed: CSV header is missing required columns: cost_usd. Expected columns: cost_usd, date, gpu_type, provider"
}
```

### Error Codes

| Status Code | Description |
|-------------|-------------|
| `400 Bad Request` | CSV format invalid, file empty, or validation failed |
| `401 Unauthorized` | Missing or invalid API key |
| `413 Payload Too Large` | File exceeds 10MB limit |
| `500 Internal Server Error` | Database operation failed |

---

## Validation Rules

### Date
- **Format:** YYYY-MM-DD (ISO 8601 date format)
- **Example:** `2024-01-15`
- **Error Examples:**
  - `2024-13-01` (invalid month)
  - `01/15/2024` (wrong format)
  - `2024-1-5` (missing leading zeros)

### Provider
- **Type:** String (non-empty)
- **Normalization:** Automatically lowercased and trimmed
- **Examples:** `AWS`, `GCP`, `Azure`, `aws`, `gcp`
- **Stored as:** `aws`, `gcp`, `azure` (lowercase)

### GPU Type
- **Type:** String (non-empty)
- **Normalization:** Automatically lowercased and trimmed
- **Examples:** `A100`, `H100`, `V100`, `a100`
- **Stored as:** `a100`, `h100`, `v100` (lowercase)

### Cost (USD)
- **Type:** Positive decimal number
- **Format:** Any valid decimal (e.g., `1245.67`, `1000`, `0.50`)
- **Precision:** Rounded to 2 decimal places
- **Error Examples:**
  - `-100.00` (must be positive)
  - `0` (must be positive)
  - `abc` (not a number)

---

## Data Processing

### Idempotency

The import process is **idempotent**:
- Records are identified by unique key: `(date, provider, gpu_type)`
- If a record already exists, only `cost_usd` is updated
- Safe to upload the same file multiple times
- Safe to upload overlapping date ranges

### Normalization

Data is automatically normalized:
- Provider names are lowercased and trimmed
- GPU types are lowercased and trimmed
- Costs are rounded to 2 decimal places

### Transaction Safety

- All records are processed in a single database transaction
- If a critical error occurs, the entire import is rolled back
- Individual row errors are logged but don't stop the import
- Successful records are committed even if some rows fail

---

## Usage Examples

### cURL

```bash
curl -X POST \
  https://api.heliox.ai/api/v1/admin/import/cost/csv \
  -H "X-API-Key: your-admin-api-key-here" \
  -F "file=@/path/to/cost_data.csv"
```

### Python (requests)

```python
import requests

url = "https://api.heliox.ai/api/v1/admin/import/cost/csv"
headers = {
    "X-API-Key": "your-admin-api-key-here"
}

with open("cost_data.csv", "rb") as f:
    files = {"file": ("cost_data.csv", f, "text/csv")}
    response = requests.post(url, headers=headers, files=files)

print(response.status_code)
print(response.json())
```

### JavaScript (fetch)

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

const response = await fetch('https://api.heliox.ai/api/v1/admin/import/cost/csv', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your-admin-api-key-here'
  },
  body: formData
});

const result = await response.json();
console.log(result);
```

---

## Logging

All import operations are logged:

**Info Level:**
- CSV parsing start/completion
- Import statistics (inserted/updated/failed)
- File name and record counts

**Warning Level:**
- Individual row validation errors
- Partial import failures

**Error Level:**
- CSV parsing errors
- Database operation failures
- Critical errors requiring rollback

**Log Format:**
```
INFO Starting CSV import from file: customer_costs.csv
INFO Successfully parsed 150 records from CSV (3 rows had errors)
INFO CSV ingestion complete: 147 inserted, 0 updated, 3 failed
INFO CSV import complete: Successfully imported 147 records: 147 inserted, 0 updated (file: customer_costs.csv)
```

---

## Troubleshooting

### Common Errors

**1. "CSV header is missing required columns"**
- **Cause:** CSV header doesn't match expected format
- **Fix:** Ensure header row is exactly: `date,provider,gpu_type,cost_usd`

**2. "Invalid date format"**
- **Cause:** Date is not in YYYY-MM-DD format
- **Fix:** Convert dates to ISO format (e.g., `2024-01-15`)

**3. "cost_usd must be positive"**
- **Cause:** Negative or zero cost values
- **Fix:** Ensure all cost values are positive numbers

**4. "File size exceeds limit"**
- **Cause:** File is larger than 10MB
- **Fix:** Split large files into smaller chunks (< 10MB each)

**5. "File encoding error"**
- **Cause:** CSV file is not UTF-8 encoded
- **Fix:** Re-save CSV file as UTF-8 encoding

### Validation Error Messages

Error messages include:
- **Row number** (for easy identification)
- **Field name** (which field has the error)
- **Expected format** (what format is required)

Example:
```
Row 45: Invalid date format '2024-13-01'. Expected YYYY-MM-DD
Row 89: cost_usd must be positive, got -100.00
Row 120: Missing provider field
```

---

## Security Considerations

1. **Admin-Only Access**
   - Endpoint requires `X-API-Key` header
   - API key must match `ADMIN_API_KEY` environment variable
   - Unauthorized requests return `401 Unauthorized`

2. **File Size Limits**
   - Maximum file size: 10MB
   - Prevents resource exhaustion
   - Larger files return `413 Payload Too Large`

3. **Input Validation**
   - All CSV data is validated before database insertion
   - Invalid data is rejected with clear error messages
   - No SQL injection risk (uses parameterized queries)

4. **Transaction Safety**
   - All imports use database transactions
   - Failed imports are rolled back
   - No partial data corruption

5. **Logging**
   - All imports are logged (with file names)
   - No sensitive data (costs, API keys) in logs
   - Request IDs for traceability

---

## Best Practices

1. **Prepare Your CSV**
   - Use the sample file as a template
   - Validate dates are in YYYY-MM-DD format
   - Ensure all cost values are positive
   - Use UTF-8 encoding

2. **Test with Small Files**
   - Start with 10-20 rows to verify format
   - Check error messages if validation fails
   - Scale up once format is confirmed

3. **Handle Errors Gracefully**
   - Check `result.failed` count in response
   - Review `result.errors` array for details
   - Fix errors and re-import if needed

4. **Idempotent Imports**
   - Safe to re-upload the same file
   - Existing records are updated (not duplicated)
   - Useful for re-processing after fixes

5. **Monitor Logs**
   - Check application logs for import status
   - Monitor for database connection issues
   - Review error patterns for data quality

---

## Support

For issues or questions:
1. Check error messages in API response
2. Review application logs for details
3. Validate CSV format against sample file
4. Verify API key is correct and has admin access

---

**End of Guide**
