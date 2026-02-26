# Heliox Tenant Onboarding Guide

## Overview

This guide covers onboarding new tenants (teams) to the Heliox platform.

## Prerequisites

- Admin access (platform admin or `ADMIN_API_KEY`)
- Tenant company name and contact

## Onboarding Steps

### 1. Create Team via Admin API

```bash
curl -X POST https://api.heliox.ai/api/v1/admin/onboard \
  -H "X-API-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "team_name": "Acme Corp",
    "api_key_name": "production"
  }'
```

**Response:**
```json
{
  "team_id": "uuid",
  "api_key": "hlx_xxxxxxxxxxxx",
  "message": "Save this API key now; it will not be shown again."
}
```

⚠️ **Critical:** The API key is returned only once. Store it securely.

### 2. Deliver Credentials to Tenant

- **Secure channel:** Use a password manager share, encrypted email, or secure portal
- **Never:** Send via plain email, Slack, or shared docs

### 3. Tenant Configuration

| Item | Action |
|------|--------|
| API Key | Provide the generated key |
| Base URL | `https://api.heliox.ai` (production) |
| Documentation | `https://api.heliox.ai/docs` |

### 4. Data Ingestion

Tenant can ingest cost data via:

- **API:** `POST /api/v1/ingest/cost` with `X-API-Key` header
- **Integrations:** Connect AWS/GCP in Settings
- **CSV Import:** Admin CSV import with team association

### 5. Verification

```bash
# Tenant verifies access
curl -H "X-API-Key: $TENANT_API_KEY" \
  https://api.heliox.ai/api/v1/me
```

Expected: `{"team_id": "...", "role": "api_key"}`

## Checklist

- [ ] Team created via admin onboard
- [ ] API key delivered securely
- [ ] Tenant can call `/api/v1/me`
- [ ] First cost data ingested
- [ ] Dashboard accessible
