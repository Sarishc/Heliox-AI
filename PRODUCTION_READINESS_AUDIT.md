# Heliox AI — Production Readiness Audit

_Last updated: 2026-03-23_

---

## Summary

| Area | Status | Notes |
|------|--------|-------|
| Auth — login / signup | Complete | Rate-limited, brute-force protected, httpOnly cookie |
| Auth — password reset | Complete | New endpoints + email flow implemented |
| Auth — email verification | Complete | Sent on signup, resend available |
| Auth — Google OAuth | Complete | Tokens encrypted at rest (Fernet) |
| Auth — SAML / SSO | Complete | Team-scoped, domain enforcement |
| Stripe billing | Complete | Webhook handles subscription + invoice events |
| AWS Cost Explorer | Complete | Real boto3 sync, incremental, idempotent |
| GCP BigQuery billing | Complete | Real google-cloud-bigquery sync |
| Azure Cost Management | Complete | Real azure-identity + httpx sync |
| Multi-tenancy | Complete | All queries scoped by team_id |
| RBAC | Complete | owner / admin / member roles enforced |
| Celery workers | Complete | 13 scheduled tasks configured |
| Token encryption | Complete | Fernet encryption on all stored OAuth tokens |
| Database migrations | Complete | Migration 028 adds email/password reset fields |
| Rate limiting | Complete | Redis-backed, OWASP-compliant login protection |
| CAPTCHA | Complete | hCaptcha on login after 3 failures |

---

## Architecture

```
Browser  ->  Next.js app (apps/app, port 3000)
                  |  /api/* proxied
             FastAPI (backend/, port 8000)
                  |
          PostgreSQL + Redis + Celery workers
                  |
          AWS Cost Explorer / GCP BigQuery / Azure Cost Management / Stripe
```

---

## Required Environment Variables

### Backend (backend/.env)

```
# REQUIRED — no defaults
SECRET_KEY=<openssl rand -hex 32>
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/heliox
REDIS_URL=redis://localhost:6379/0
INTEGRATIONS_ENCRYPTION_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# App
ENV=production
LOG_LEVEL=INFO
FRONTEND_URL=https://your-app.com
API_BASE_URL=https://your-api.com

# Email (Resend — required for password reset + email verification)
RESEND_API_KEY=re_...
EMAIL_FROM=noreply@your-app.com

# Stripe (required for billing)
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_STARTER=price_...
STRIPE_PRICE_ID_GROWTH=price_...
STRIPE_PRICE_ID_ENTERPRISE=price_...

# Google OAuth (optional)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://your-api.com/api/v1/auth/oauth/google/callback

# CORS (must match exact frontend domain in production)
CORS_ORIGINS=["https://your-app.com"]
CORS_ENABLED=true

# Security
CSRF_PROTECTION_ENABLED=true
AUTH_COOKIE_SECURE=true
HCAPTCHA_SECRET_KEY=...

# Sentry (optional)
SENTRY_DSN=https://...
SENTRY_ENVIRONMENT=production
```

### Frontend (apps/app/.env.local)

```
NEXT_PUBLIC_API_URL=https://your-api.com
NEXT_PUBLIC_HCAPTCHA_SITE_KEY=...
```

---

## Running Migrations

```bash
cd backend
alembic upgrade head
```

Migration 028 adds to `users` table:
- `email_verified` (boolean, default false)
- `email_verification_token` (varchar 64, unique, nullable)
- `password_reset_token` (varchar 64, unique, nullable)
- `password_reset_token_expires_at` (timestamptz, nullable)

---

## New Endpoints (from this hardening session)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | /api/v1/auth/forgot-password | Public | Request password reset email |
| POST | /api/v1/auth/reset-password | Public | Consume token, set new password |
| GET | /api/v1/auth/verify-email?token=... | Public | Verify email from signup link |
| POST | /api/v1/auth/resend-verification | Public | Re-send verification email |

All public endpoints return 202 with a generic message to prevent email enumeration.

---

## Testing Password Reset Locally

```bash
# 1. Request reset (check logs for URL if RESEND_API_KEY is not set)
curl -X POST http://localhost:8000/api/v1/auth/forgot-password \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'

# 2. Get raw token from backend log line "Password reset email queued for user..."
#    or from email if Resend is configured

# 3. Reset the password
curl -X POST http://localhost:8000/api/v1/auth/reset-password \
  -H "Content-Type: application/json" \
  -d '{"token": "RAW_TOKEN_HERE", "new_password": "newpassword123"}'
```

## Testing Stripe Webhooks Locally

```bash
# Install stripe CLI then:
stripe listen --forward-to localhost:8000/api/v1/billing/webhook

# Trigger events:
stripe trigger invoice.paid
stripe trigger invoice.payment_failed
stripe trigger customer.subscription.updated
```

---

## Stripe Webhook Events Handled

| Event | Action |
|-------|--------|
| customer.subscription.created | Sync plan + entitlements to DB |
| customer.subscription.updated | Re-sync plan + entitlements |
| customer.subscription.deleted | Downgrade to free plan |
| checkout.session.completed | Logged for audit (subscription events do the sync) |
| invoice.paid | Re-sync subscription status (ensures active state) |
| invoice.payment_failed | Mark subscription past_due in DB + log for support |

---

## OAuth Token Security

Refresh tokens and access tokens from Google OAuth are now encrypted at rest
using Fernet symmetric encryption (same key as `INTEGRATIONS_ENCRYPTION_KEY`).

- Encrypted on write in `upsert_oauth_identity()`
- Decrypted only when needed via `get_decrypted_refresh_token()` / `get_decrypted_access_token()`
- Never logged or returned to frontend
- Columns named `access_token_encrypted` / `refresh_token_encrypted` to make storage intent clear

Existing plaintext tokens in the DB (before this migration) will fail to decrypt.
Those users will be asked to re-authenticate via Google OAuth to get new encrypted tokens.

---

## Remaining Optional Improvements

- Move OAuth state cache from Python dict to Redis (required for multi-instance deploys)
- Implement JWT refresh token rotation (currently: 30-min access tokens only)
- Add GDPR data export and account deletion endpoints
- Implement email unsubscribe tokens for alert emails
- Add admin UI for subscription + team management
