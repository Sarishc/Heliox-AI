# Saved Reports & Exports - Implementation Checklist

## Backend Files ✓

- [x] Models: backend/app/models/reporting.py
- [x] Migration: backend/alembic/versions/015_add_saved_reports.py
- [x] Schemas: backend/app/schemas/reporting.py
- [x] Service: backend/app/services/reports.py
- [x] Routes (protected): backend/app/api/routes/reports.py
- [x] Routes (public): backend/app/api/routes/share.py
- [x] Config updates: backend/app/core/config.py
- [x] API router registration: backend/app/api/__init__.py
- [x] Main app updates: backend/app/main.py
- [x] Dependencies: backend/requirements.txt (added reportlab)
- [x] Tests: backend/tests/test_reports.py

## Frontend Files ✓

- [x] Reports page: apps/app/app/reports/page.tsx
- [x] Share page: apps/app/app/share/[token]/page.tsx
- [x] Navigation: apps/app/components/AppShell.tsx (added Reports item)

## Documentation ✓

- [x] Quickstart guide: docs/QUICKSTART.md (added reports section)
- [x] Implementation summary: REPORTS_IMPLEMENTATION.md

## Verification Commands

### 1. Check all files exist
\`\`\`bash
# Backend
ls backend/app/models/reporting.py
ls backend/app/schemas/reporting.py
ls backend/app/services/reports.py
ls backend/app/api/routes/reports.py
ls backend/app/api/routes/share.py
ls backend/alembic/versions/015_add_saved_reports.py
ls backend/tests/test_reports.py

# Frontend
ls apps/app/app/reports/page.tsx
ls apps/app/app/share/\[token\]/page.tsx

# Docs
ls docs/QUICKSTART.md
ls REPORTS_IMPLEMENTATION.md
\`\`\`

### 2. Verify Python syntax
\`\`\`bash
cd backend
python -m py_compile app/models/reporting.py
python -m py_compile app/schemas/reporting.py
python -m py_compile app/services/reports.py
python -m py_compile app/api/routes/reports.py
python -m py_compile app/api/routes/share.py
python -m py_compile alembic/versions/015_add_saved_reports.py
\`\`\`

### 3. Run migration (requires Docker)
\`\`\`bash
docker compose up -d
docker compose exec api alembic upgrade head
# Should see: "015 -> head"
\`\`\`

### 4. Run tests (requires Docker or venv)
\`\`\`bash
# Option 1: Docker
docker compose exec api pytest tests/test_reports.py -v

# Option 2: Local venv (if set up)
cd backend
source .venv/bin/activate
pytest tests/test_reports.py -v
\`\`\`

### 5. Manual API test
\`\`\`bash
# Get API key first
export API_KEY="your-api-key"

# Create report
curl -X POST http://localhost:8000/api/v1/reports \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Report",
    "description": "Testing implementation",
    "config": {
      "start_date": "2026-01-01",
      "end_date": "2026-01-31",
      "environment": "prod",
      "sections": ["kpis", "daily_spend"]
    }
  }'

# List reports
curl http://localhost:8000/api/v1/reports \
  -H "X-API-Key: $API_KEY"
\`\`\`

### 6. Frontend verification (requires Next.js running)
\`\`\`bash
cd apps/app
npm run dev
# Visit: http://localhost:3000/reports
\`\`\`

## Implementation Complete ✓

All deliverables from the plan have been implemented:

1. ✓ Models + migrations
2. ✓ Schemas + CRUD/run/share routes
3. ✓ CSV/PDF generation + storage
4. ✓ Reports UI + share page
5. ✓ Tests + docs

## Next Steps

1. Start Docker: \`docker compose up -d\`
2. Run migration: \`docker compose exec api alembic upgrade head\`
3. Access UI: http://localhost:3000/reports
4. Follow QUICKSTART.md section 13 for usage guide

## Known Issues to Check

- [ ] Verify storage directory is created: \`mkdir -p data/reports\`
- [ ] Check file permissions if running locally
- [ ] Ensure REPORT_STORAGE_PATH in .env if custom location needed
- [ ] Test share links with REPORT_SHARE_BASE_URL set correctly

