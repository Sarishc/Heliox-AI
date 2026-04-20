# Heliox AI — Revenue Launch Checklist

Work through this list top-to-bottom before accepting first paying customer.

---

## Infrastructure

- [ ] PostgreSQL on managed service (RDS, Supabase, Neon, Railway) with daily backups
- [ ] Redis on managed service (Upstash, Railway, ElastiCache) — required for sessions + Celery
- [ ] SSL/TLS certificate on both frontend domain and API domain
- [ ] Run `alembic upgrade head` on production database (includes migration 028)
- [ ] Celery worker and beat containers running and healthy
- [ ] Health endpoint responding: `GET /api/v1/health`

## Environment Variables

- [ ] `SECRET_KEY` set (unique, 32+ random hex bytes — NEVER share)
- [ ] `DATABASE_URL` pointing to production Postgres
- [ ] `REDIS_URL` pointing to production Redis
- [ ] `INTEGRATIONS_ENCRYPTION_KEY` set (Fernet key — back this up securely)
- [ ] `ENV=production`
- [ ] `AUTH_COOKIE_SECURE=true`
- [ ] `CSRF_PROTECTION_ENABLED=true`
- [ ] `CORS_ORIGINS` set to exact production frontend URL(s)
- [ ] `FRONTEND_URL` set (used in reset + verification email links)
- [ ] `API_BASE_URL` set (used in OAuth redirect URIs)

## Email (Resend)

- [ ] Resend account created, sending domain verified (DNS SPF + DKIM records set)
- [ ] `RESEND_API_KEY` configured
- [ ] `EMAIL_FROM` set to verified domain address (e.g., noreply@heliox.ai)
- [ ] Test: signup a new account → verify email arrives
- [ ] Test: request password reset → verify reset email arrives
- [ ] Test: reset link opens `/reset-password` page correctly

## Stripe

- [ ] Stripe account in live mode (not test mode)
- [ ] Products created: Starter ($49/mo), Growth ($199/mo), Enterprise (custom)
- [ ] Price IDs set: `STRIPE_PRICE_ID_STARTER`, `STRIPE_PRICE_ID_GROWTH`, `STRIPE_PRICE_ID_ENTERPRISE`
- [ ] `STRIPE_SECRET_KEY` set to `sk_live_...`
- [ ] Webhook endpoint registered in Stripe dashboard: `POST https://your-api.com/api/v1/billing/webhook`
- [ ] Webhook events enabled: `customer.subscription.*`, `checkout.session.completed`, `invoice.paid`, `invoice.payment_failed`
- [ ] `STRIPE_WEBHOOK_SECRET` set to `whsec_...` from Stripe dashboard
- [ ] Test: run `stripe trigger invoice.paid` with Stripe CLI, verify subscription stays active in DB
- [ ] Test: run `stripe trigger invoice.payment_failed`, verify subscription marked `past_due` in DB
- [ ] Test: complete checkout flow end-to-end in live mode with a real card (then refund)

## Auth & Signup

- [ ] Signup flow tested: create account → verification email received → email verified → login works
- [ ] Password reset tested: forgot-password → email → reset link → new password → login
- [ ] Google OAuth tested (if configured): login → redirect → dashboard
- [ ] Demo mode disabled or clearly separated from production accounts
- [ ] Rate limiting working: 5 failed logins → lockout for 15 min

## Cloud Integrations

- [ ] AWS: create IAM user with `ce:GetCostAndUsage`, `sts:GetCallerIdentity` permissions
- [ ] AWS: test integration connection from Settings → Integrations → AWS
- [ ] GCP: enable BigQuery billing export in GCP console; create service account with BigQuery Data Viewer
- [ ] GCP: test integration connection from Settings → Integrations → GCP
- [ ] Azure: create App Registration with `Cost Management Reader` role
- [ ] Azure: test integration connection from Settings → Integrations → Azure

## Team & Billing UX

- [ ] Billing page shows correct plan for paid subscribers
- [ ] Upgrade flow (Starter / Growth) completes end-to-end
- [ ] Customer portal accessible (for plan changes and cancellation)
- [ ] Downgrade / cancellation reflected in DB after webhook

## Legal & Compliance

- [ ] Privacy Policy published and linked in app footer
- [ ] Terms of Service published and linked in app footer
- [ ] Cookie consent banner (if serving EU users)
- [ ] Data Processing Agreement template ready for enterprise customers

## Monitoring

- [ ] Sentry configured (SENTRY_DSN set) — captures uncaught exceptions
- [ ] Uptime monitor set up (e.g., BetterUptime, UptimeRobot) on `/api/v1/health`
- [ ] Log aggregation configured (e.g., Papertrail, Datadog, Logtail)
- [ ] Celery task failure alerts configured

## Pre-launch Smoke Test

Run through this exact sequence on production:
1. [ ] Create account with a real email
2. [ ] Receive and click verification email
3. [ ] Log in
4. [ ] Connect one cloud provider (AWS, GCP, or Azure)
5. [ ] Verify cost data appears on dashboard after first sync (~5 min)
6. [ ] Set a budget policy
7. [ ] Upgrade to Starter plan via Stripe checkout
8. [ ] Verify plan shown as Starter in Settings → Billing
9. [ ] Log out
10. [ ] Reset password via forgot-password flow
11. [ ] Log back in with new password
