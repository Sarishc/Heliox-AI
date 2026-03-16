# Environment Variables Setup

This document describes required and optional environment variables for Heliox AI.

## Quick Start (Local Development)

```bash
# Backend
cd backend
cp .env.example .env
# Edit .env and set SECRET_KEY (required):
#   openssl rand -hex 32
# Optionally set ADMIN_API_KEY for demo/scripts:
#   openssl rand -hex 24

# Frontend (optional - for demo bootstrap)
cd apps/app
cp .env.local.example .env.local
# Set NEXT_PUBLIC_DEV_ADMIN_API_KEY to match backend ADMIN_API_KEY for "Try demo" button
```

## Required Variables

| Variable | Description | Generate |
|----------|-------------|----------|
| `SECRET_KEY` | JWT signing key (min 32 chars) | `openssl rand -hex 32` |
| `ADMIN_API_KEY` | Admin API key for scripts/demo (when not using RBAC) | `openssl rand -hex 24` |

**Production:** `SECRET_KEY` must be set and must not contain insecure patterns (`dev-secret`, `change-me`, etc.). The app will fail to start if invalid.

## Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | (docker-compose default) | PostgreSQL connection string |
| `REDIS_URL` | (docker-compose default) | Redis connection string |
| `ADMIN_API_KEY` | (empty) | Admin endpoints; empty = use platform admin only |
| `INTEGRATIONS_ENCRYPTION_KEY` | (empty) | Fernet key for integration configs |
| `SLACK_WEBHOOK_URL` | (empty) | Slack alerts |
| `STRIPE_*` | (empty) | Billing |
| `GOOGLE_CLIENT_*` | (empty) | OAuth SSO |

## Frontend (NEXT_PUBLIC_*)

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | Backend API URL (required in production) |
| `NEXT_PUBLIC_DEV_ADMIN_API_KEY` | **Dev only** - for "Try demo" button. Never set in production. |

## Scripts Requiring Env Vars

- `scripts/create-team-key.sh` - requires `ADMIN_API_KEY`
- `scripts/demo.sh` - requires `ADMIN_API_KEY`
- `scripts/test-golden-path.sh` - requires `ADMIN_API_KEY`
- `test_job_analytics.sh` - requires `ADMIN_API_KEY`, `TEST_USER`, `TEST_PASSWORD`
- `test_api.sh` - requires `TEST_USER`, `TEST_PASSWORD`
- `load-test/run-load-test.sh` - requires `HELIOX_ADMIN_API_KEY` or `ADMIN_API_KEY`

## Production Checklist

- [ ] `SECRET_KEY` set and secure (32+ chars, no insecure patterns)
- [ ] `DATABASE_URL` uses strong password (not `postgres:postgres`)
- [ ] `REDIS_URL` explicitly set (not localhost default)
- [ ] `CORS_ORIGINS` set to production domains only
- [ ] `NEXT_PUBLIC_DEV_ADMIN_API_KEY` **not** set in frontend
