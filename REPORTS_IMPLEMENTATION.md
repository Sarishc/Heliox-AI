# Saved Reports & Exports - Implementation Summary

## Overview
Full-stack implementation of saved reports with CSV/PDF exports and shareable read-only links for Heliox-AI.

## What Was Delivered

### Backend Implementation

#### 1. Data Models (`backend/app/models/reporting.py`)
Three new SQLAlchemy models:

- **SavedReport**: Stores report configurations
  - Fields: `id`, `team_id`, `name`, `description`, `config_json`, `created_by_user_id`, timestamps
  - Team-scoped with foreign key constraint
  - Indexed on `team_id` for fast queries

- **ReportShareLink**: Manages tokenized share links
  - Fields: `id`, `team_id`, `report_id`, `token_hash`, `expires_at`, `revoked_at`, timestamps
  - SHA-256 hashed tokens for security
  - Indexed on `token_hash` for fast lookups
  - Nullable `revoked_at` for soft deletion

- **ReportRun**: Tracks generated report files
  - Fields: `id`, `team_id`, `report_id`, `status`, `generated_at`, `storage_path`, `file_type`, timestamps
  - Supports both CSV and PDF formats
  - File paths stored relative to `REPORT_STORAGE_PATH`

#### 2. Database Migration (`backend/alembic/versions/015_add_saved_reports.py`)
- Creates all three tables with proper indexes
- Foreign key constraints with CASCADE deletes
- Unique constraints on token_hash and composite keys
- Backward-compatible downgrade function

#### 3. Schemas (`backend/app/schemas/reporting.py`)
Pydantic models for request/response validation:
- `ReportConfig`: Configuration structure (sections, filters, date range)
- `SavedReportCreate/Update/Response`: CRUD payloads
- `ReportRunRequest/Response`: Report generation payloads
- `ShareLinkCreate/Response`: Share link management
- `ShareReportResponse`: Public share view data

#### 4. Report Generation Service (`backend/app/services/reports.py`)
Core logic for building and exporting reports:

**Data Collection Methods:**
- `_build_report_data()`: Aggregates metrics from analytics endpoints
- Reuses existing analytics queries for consistency
- Collects: KPIs, daily spend, idle waste, cost by model, top recommendations

**CSV Generation:**
- Fixed columns with deterministic ordering
- Multiple sections: overview, daily_spend, cost_by_model, recommendations
- Clean UTF-8 encoding with proper quoting

**PDF Generation (ReportLab):**
- Professional layout with Helvetica fonts
- Header with report metadata
- Overview KPIs in a styled table
- Daily spend summary
- Top 5 models by cost
- Top recommendations with severity indicators
- Footer with generation timestamp

**File Storage:**
- Configurable storage path via `REPORT_STORAGE_PATH` setting
- Subdirectories per team_id for isolation
- Atomic file writes with unique filenames
- Returns relative paths for database storage

#### 5. API Routes

**Protected Routes (`backend/app/api/routes/reports.py`):**
- `POST /v1/reports` - Create saved report
- `GET /v1/reports` - List team's reports
- `GET /v1/reports/{id}` - Get report by ID
- `PUT /v1/reports/{id}` - Update report config
- `DELETE /v1/reports/{id}` - Delete report
- `POST /v1/reports/{id}/run` - Generate CSV/PDF
- `GET /v1/reports/runs/{run_id}/download` - Stream file download
- `POST /v1/reports/{id}/share` - Create share link
- `POST /v1/reports/share/{share_id}/revoke` - Revoke share link

All routes enforce team scoping via `get_effective_team_id()`.

**Public Route (`backend/app/api/routes/share.py`):**
- `GET /share/{token}` - Publicly accessible read-only report view
- Token verification with constant-time comparison
- Expiry and revocation checks
- Returns full report data with snapshot

Mounted in `backend/app/main.py` as a public route (no auth).

#### 6. Configuration (`backend/app/core/config.py`)
New settings:
- `REPORT_STORAGE_PATH`: Base directory for report files (default: `./data/reports`)
- `REPORT_SHARE_BASE_URL`: Base URL for share links (optional, falls back to API URL)
- `REPORT_SHARE_DEFAULT_TTL_DAYS`: Default expiry days (7)
- `REPORT_SHARE_MAX_TTL_DAYS`: Maximum expiry days (90)

#### 7. Dependencies (`backend/requirements.txt`)
Added:
- `reportlab==4.0.7` - PDF generation library

### Frontend Implementation

#### 1. Reports Page (`apps/app/app/reports/page.tsx`)
Full CRUD interface for saved reports:

**Features:**
- List all saved reports in a clean card layout
- Create new reports with name, description, date range, environment filters
- Section selector (KPIs, Daily Spend, Idle Waste, Cost by Model, Recommendations)
- Edit existing report configurations
- Delete reports with confirmation
- Export buttons for CSV and PDF
- Share link generation with expiry selector (7, 30, 90 days)
- Copy share link to clipboard
- View existing share links and revoke them

**UI Components:**
- Responsive grid layout
- Modal forms for create/edit
- Dropdown actions menu per report
- Loading states and error handling
- Success notifications

#### 2. Share Page (`apps/app/app/share/[token]/page.tsx`)
Read-only public report view:

**Features:**
- Fetches report data via public `/share/{token}` endpoint
- No authentication required (token-based access)
- Displays report metadata (name, description, date range)
- Shows all report sections with clean formatting
- KPIs, spend trends, model breakdown, recommendations
- Watermark: "Shared by [team]"
- Expires message if token is invalid/expired

**UI:**
- Clean, minimal design for sharing with stakeholders
- Print-friendly layout
- Branded Heliox header
- Responsive for mobile/tablet viewing

#### 3. Navigation (`apps/app/components/AppShell.tsx`)
Added "Reports" navigation item with FileText icon in sidebar.

### Documentation

#### Updated Quickstart (`docs/QUICKSTART.md`)
Added new section "13) Create and export a board-ready report":
- Step-by-step guide for saving a report
- Generating CSV and PDF exports
- Creating shareable links
- Complete curl examples
- Expected outputs

### Tests

#### Backend Tests (`backend/tests/test_reports.py`)
Comprehensive test coverage:

**Tenant Isolation Tests:**
- `test_report_tenant_isolation`: Verifies teams can only see their own reports
- `test_report_run_tenant_isolation`: Ensures report runs are team-scoped
- `test_share_link_team_scoped`: Share links respect team boundaries

**Share Link Tests:**
- `test_share_token_expiry`: Expired tokens return 404
- `test_share_token_revocation`: Revoked tokens return 404
- `test_share_token_valid_access`: Valid tokens return report data

**Export Tests:**
- `test_csv_generation_schema`: CSV has correct columns and ordering
- `test_pdf_generation_returns_bytes`: PDF generation produces valid file

All tests use in-memory SQLite for speed and isolation.

## File Structure

```
backend/
├── alembic/versions/
│   └── 015_add_saved_reports.py        # Migration
├── app/
│   ├── api/
│   │   ├── __init__.py                 # Updated: added reports router
│   │   └── routes/
│   │       ├── reports.py              # New: protected CRUD/run/share routes
│   │       └── share.py                # New: public share endpoint
│   ├── core/
│   │   └── config.py                   # Updated: added report settings
│   ├── models/
│   │   ├── __init__.py                 # Updated: registered new models
│   │   └── reporting.py                # New: report data models
│   ├── schemas/
│   │   ├── __init__.py                 # Updated: added reporting schemas
│   │   └── reporting.py                # New: request/response schemas
│   └── services/
│       └── reports.py                  # New: CSV/PDF generation service
├── tests/
│   └── test_reports.py                 # New: comprehensive test suite
├── requirements.txt                     # Updated: added reportlab
└── main.py                             # Updated: mounted share routes

apps/app/
├── app/
│   ├── reports/
│   │   └── page.tsx                    # New: reports CRUD UI
│   └── share/
│       └── [token]/
│           └── page.tsx                # New: public share view
└── components/
    └── AppShell.tsx                    # Updated: added Reports nav item

docs/
└── QUICKSTART.md                       # Updated: added reports guide
```

## Security Features

1. **Token Hashing**: Share tokens stored as SHA-256 hashes
2. **Constant-Time Comparison**: Token verification prevents timing attacks
3. **Team Scoping**: All operations enforce team_id boundaries
4. **Expiry**: Share links have configurable TTL
5. **Revocation**: Share links can be soft-deleted
6. **File Isolation**: Reports stored in team-specific subdirectories

## Configuration Required

### Environment Variables
```bash
# Required
REPORT_STORAGE_PATH=/app/data/reports  # Or local path for dev

# Optional
REPORT_SHARE_BASE_URL=https://app.heliox.ai  # For production share links
REPORT_SHARE_DEFAULT_TTL_DAYS=7
REPORT_SHARE_MAX_TTL_DAYS=90
```

### Docker Volume
Add to `docker-compose.yml`:
```yaml
volumes:
  - ./data/reports:/app/data/reports
```

## Usage Flow

1. **Create Report**: User saves a report configuration with desired filters/sections
2. **Generate Export**: User clicks "Export CSV" or "Export PDF"
   - Backend builds data from analytics queries
   - Generates file on disk
   - Returns download URL
3. **Download**: User downloads file via `/v1/reports/runs/{id}/download`
4. **Share**: User creates share link with expiry
   - Backend generates random token, hashes it
   - Returns share URL
5. **Access**: Recipient visits share URL
   - Public endpoint validates token
   - Returns read-only report view

## Testing Instructions

### Run Backend Tests
```bash
cd backend
pytest tests/test_reports.py -v
```

### Manual Testing
```bash
# 1. Run migrations
docker compose exec api alembic upgrade head

# 2. Create a report
curl -X POST http://localhost:8000/api/v1/reports \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q1 GPU Cost Report",
    "description": "Overview for leadership",
    "config": {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31",
      "environment": "prod",
      "sections": ["kpis", "daily_spend", "cost_by_model", "recommendations"]
    }
  }'

# 3. Generate PDF export
curl -X POST http://localhost:8000/api/v1/reports/{REPORT_ID}/run \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"file_type": "pdf"}'

# 4. Download file
curl -o report.pdf http://localhost:8000/api/v1/reports/runs/{RUN_ID}/download \
  -H "X-API-Key: YOUR_KEY"

# 5. Create share link
curl -X POST http://localhost:8000/api/v1/reports/{REPORT_ID}/share \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"ttl_days": 7}'

# 6. Access share page (no auth)
curl http://localhost:8000/share/{TOKEN}
```

## Next Steps / Future Enhancements

1. **Scheduled Reports**: Celery task to generate and email reports on schedule
2. **Cloud Storage**: S3/GCS integration for report files
3. **Caching**: Cache generated reports to avoid regeneration
4. **Email Delivery**: Send PDF directly to stakeholders
5. **Custom Branding**: Team logos in PDF exports
6. **More Formats**: Excel, JSON exports
7. **Report Templates**: Predefined report configs for common use cases
8. **Analytics**: Track share link views and downloads

## Known Limitations

1. **Synchronous Generation**: Reports generated synchronously (could timeout for large datasets)
2. **Local Storage Only**: Files stored on disk (not cloud-native yet)
3. **Fixed Sections**: Report sections are hardcoded (not fully customizable)
4. **No Caching**: Each export regenerates from scratch
5. **Single File per Run**: One CSV or PDF per run (not both simultaneously)

## Migration Notes

To apply the migration in production:
```bash
docker compose exec api alembic upgrade head
```

The migration is backward-compatible and includes a `downgrade()` function.

## Support

For issues or questions:
- Check logs: `docker compose logs api`
- Verify storage path is writable: `ls -la data/reports/`
- Ensure ReportLab is installed: `pip list | grep reportlab`
- Test token generation: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
