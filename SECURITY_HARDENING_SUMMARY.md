# Heliox AI — Security Hardening Summary

_Last updated: 2026-03-23_

This document describes the security posture of the Heliox AI platform and the
hardening work completed in this session.

---

## Hardening Applied (This Session)

### 1. OAuth Refresh Token Encryption

**Risk before:** Google OAuth refresh tokens were stored as plaintext strings in the
`oauth_identities` table (explicit `# TODO: Encrypt` comments in code).
A database breach would expose tokens usable to access users' Google accounts.

**Fix:** Tokens are now encrypted with Fernet (`INTEGRATIONS_ENCRYPTION_KEY`) before
any DB write in `upsert_oauth_identity()`. Decryption happens only in-process via
`get_decrypted_refresh_token()` / `get_decrypted_access_token()` in `oauth_google.py`.

**Transition:** Existing plaintext tokens in the DB will fail to decrypt — users will
be prompted to re-authenticate via Google OAuth. This is the safe, correct behavior.

---

### 2. Password Reset Flow

**Risk before:** No password reset mechanism existed. Users who forgot their password
had no self-service recovery path, and support would need direct DB access.

**Implemented:**
- `POST /api/v1/auth/forgot-password` — rate-limited, always returns 202 (no email enumeration)
- `POST /api/v1/auth/reset-password` — validates token expiry (60 min), single-use, hashed in DB
- Frontend pages: `/forgot-password` and `/reset-password`
- Token stored as SHA-256 hash in DB; raw token sent only via email
- Token is invalidated immediately on successful use

---

### 3. Email Verification

**Risk before:** Users could sign up with any email address without proving ownership.
This enables spam, impersonation, and audit failures.

**Implemented:**
- `email_verified` field added to `users` table (migration 028)
- Verification token generated at signup, emailed immediately
- `GET /api/v1/auth/verify-email?token=...` — verifies and clears token
- `POST /api/v1/auth/resend-verification` — resend for expired/lost emails
- Frontend page: `/verify-email`
- Token stored as SHA-256 hash; idempotent if already verified

---

### 4. Stripe Webhook Hardening

**Risk before:** `invoice.paid` and `invoice.payment_failed` events were not handled.
Failed payments would not reflect in the DB, allowing past-due subscribers to retain
paid-tier access indefinitely.

**Implemented:**
- `invoice.paid` → re-syncs subscription from Stripe API (ensures `active` status)
- `invoice.payment_failed` → immediately marks subscription `past_due` in DB
- Webhook processing errors now return 200 (prevents Stripe retry storm on code bugs)
- Full event audit logging

---

## Existing Security Controls (Pre-existing)

| Control | Implementation |
|---------|---------------|
| Password hashing | Bcrypt via passlib |
| Session tokens | JWT HS256, 30-min expiry, httpOnly cookie |
| Token blacklisting | Redis-backed on logout |
| Brute force protection | 5 attempts/min per IP, 15-min lockout, CAPTCHA after 3 |
| Integration credentials | Fernet encrypted at rest (`config_encrypted` column) |
| Multi-tenant isolation | All queries scoped to `team_id` |
| RBAC | owner / admin / member enforced on all sensitive routes |
| Stripe webhook verification | Signature verified with `STRIPE_WEBHOOK_SECRET` |
| CORS | Configurable, defaults to none in production |
| CSRF | Configurable (`CSRF_PROTECTION_ENABLED`) |
| Slack webhooks | Fernet encrypted in DB (migration 023) |
| SAML SSO | python3-saml, domain enforcement, state validation |
| OAuth state | CSRF protection via state parameter (move to Redis for multi-instance) |

---

## Token Storage — Before / After

| Token type | Before | After |
|-----------|--------|-------|
| Google access token | Plaintext in DB | Fernet encrypted |
| Google refresh token | Plaintext in DB | Fernet encrypted |
| Integration credentials (AWS keys, GCP SA JSON, Azure secrets) | Fernet encrypted | Fernet encrypted (unchanged) |
| Password reset token | Did not exist | SHA-256 hash in DB, raw token in email only |
| Email verification token | Did not exist | SHA-256 hash in DB, raw token in email only |
| Session JWT | In httpOnly cookie | In httpOnly cookie (unchanged) |
| Slack webhook URL | Fernet encrypted | Fernet encrypted (unchanged) |

---

## Encryption Key Management

All symmetric encryption uses `INTEGRATIONS_ENCRYPTION_KEY` (Fernet format).

**To generate a new key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

**Key rotation procedure:**
1. Generate new key
2. Run a migration script that decrypts each row with the old key and re-encrypts with the new key
   (use `IntegrationEncryption.rotate_key()` helper in `backend/app/integrations/encryption.py`)
3. Update `INTEGRATIONS_ENCRYPTION_KEY` in all environments
4. Restart all API and worker processes

**CRITICAL:** Back up this key separately from the database. Loss of the key means
loss of all encrypted credentials (cloud integration configs and OAuth tokens).

---

## Remaining Security Work (Lower Priority)

| Item | Priority | Notes |
|------|----------|-------|
| Move OAuth state cache to Redis | High | In-memory cache breaks with multiple API instances |
| JWT refresh token rotation | Medium | Current 30-min tokens are short enough for many use cases |
| Column-level encryption for email addresses | Low | Adds complexity; consider if GDPR requirement arises |
| Admin audit log for all destructive actions | Medium | Partial (audit_log table exists) |
| Automated secret scanning in CI | Medium | GitHub secret scanning or truffleHog |
| Penetration test | High (before Series A) | Engage external security firm |
