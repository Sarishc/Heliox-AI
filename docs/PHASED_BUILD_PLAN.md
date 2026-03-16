# Heliox AI — Phased Build Plan

**Based on:** Production & Market Readiness Audit  
**Purpose:** Structured roadmap from MVP improvements to growth features

---

## Phase 1 — MVP Improvements

**Goal:** Fix critical blockers and make the product demo-ready for YC and early customers.  
**Timeline:** 2–3 weeks  
**Complexity:** Low–Medium

### Features

| Feature | Description |
|---------|-------------|
| Celery Beat fix | Scheduled jobs run reliably in production |
| Credential hygiene | No hardcoded secrets; env-based config |
| Onboarding wizard | Guided 3-step flow: team → cloud → first data |
| Billing usage UI | Re-enable and surface usage in Settings |
| Empty states | Helpful messaging when no data is connected |
| Error handling | Clear UX for API failures, 401, rate limits |

### Engineering Tasks

| Task | Description | Owner |
|------|-------------|-------|
| Fix Celery Beat | Mount writable volume for `celerybeat-schedule`; fix permissions | Backend |
| Env config | Replace hardcoded values in docker-compose with `env_file` / SSM | DevOps |
| Sentry setup | Add `SENTRY_DSN` to prod env; verify error capture | DevOps |
| Onboarding wizard | Multi-step flow component; progress indicator | Frontend |
| Billing usage API | Re-enable `/api/v1/billing/usage` in router | Backend |
| Empty state components | `EmptyState` for dashboard, analytics, forecast | Frontend |
| API error UX | Toast/alert for 401, 429, 5xx with retry CTA | Frontend |

### Database Changes

| Change | Type | Description |
|--------|------|-------------|
| None required | — | Phase 1 uses existing schema |

### APIs Required

| API | Method | Description |
|-----|--------|-------------|
| `GET /api/v1/billing/usage` | Existing | Re-enable; returns usage rollups |
| `GET /api/v1/me` | Existing | Used by onboarding to check team |
| `POST /api/v1/onboarding/welcome` | Existing | Create team + first API key |
| `GET /api/v1/integrations` | Existing | List connections for onboarding |

### UI Changes

| Page/Component | Change |
|----------------|--------|
| `/onboarding` | Convert to 3-step wizard: (1) Team name, (2) Connect AWS/GCP or skip, (3) Success + CTA to dashboard |
| `/settings/billing` | Add Usage section with last 30 days chart; link to Stripe portal |
| Dashboard | Add `EmptyState` when no cost data: "Connect AWS or GCP to see costs" |
| Analytics | Add `EmptyState` when no data |
| Forecast | Add `EmptyState` when no history |
| Global | Error boundary + toast for API failures |

### Estimated Complexity

| Area | Complexity | Notes |
|------|------------|-------|
| Celery Beat | Low | Config change |
| Env/Secrets | Low | 1–2 hours |
| Onboarding wizard | Medium | 3–5 days |
| Billing usage UI | Low | 2–4 hours |
| Empty states | Low | 1–2 days |
| **Phase 1 Total** | **Medium** | **~2–3 weeks** |

---

## Phase 2 — SaaS Infrastructure

**Goal:** Production-grade deployment, observability, and reliability.  
**Timeline:** 3–4 weeks  
**Complexity:** Medium

### Features

| Feature | Description |
|---------|-------------|
| CD pipeline | Deploy to staging and production on merge |
| Secrets management | SSM/Secrets Manager; no secrets in repo |
| Prometheus metrics | HTTP latency, error rate, request count |
| Log aggregation | Structured logs to CloudWatch/Datadog |
| Health checks | `/health`, `/ready`, `/liveness` with DB/Redis checks |
| Slack webhook encryption | Encrypt at rest; decrypt on use |
| Webhook retries | Retry Slack with backoff; dead-letter queue |
| Connection pooling | Tune for production load |

### Engineering Tasks

| Task | Description | Owner |
|------|-------------|-------|
| GitHub Actions CD | Add deploy jobs: staging (main), production (tag) | DevOps |
| Terraform secrets | Move secrets to SSM; reference in ECS task def | DevOps |
| Prometheus middleware | Record `heliox_http_requests_total`, latency histogram | Backend |
| Logging config | JSON format; request_id; log level from env | Backend |
| Slack encryption | Encrypt webhook URL with Fernet; store ciphertext | Backend |
| Webhook retry | Celery task with exponential backoff; max 5 retries | Backend |
| DB pool tuning | `pool_size=30`, `max_overflow=50` for prod | Backend |
| Migration tests | Add test that runs migrations up/down | Backend |

### Database Changes

| Change | Type | Description |
|--------|------|-------------|
| `alert_settings.slack_webhook_encrypted` | New column | Store encrypted webhook; migrate existing |
| `webhook_delivery_log` | New table | Optional: log delivery status for debugging |

### APIs Required

| API | Method | Description |
|-----|--------|-------------|
| `GET /health` | Existing | Liveness |
| `GET /ready` | Existing | Readiness (DB + Redis) |
| `GET /metrics` | Existing | Prometheus scrape |
| `PUT /api/v1/alert-settings/webhook` | Modify | Accept encrypted payload or encrypt server-side |

### UI Changes

| Page/Component | Change |
|----------------|--------|
| Settings > Alerts | No change; encryption is backend-only |
| Admin (if any) | Add link to Grafana/Prometheus for internal use |

### Estimated Complexity

| Area | Complexity | Notes |
|------|------------|-------|
| CD pipeline | Medium | 2–3 days |
| Secrets | Low | 1 day |
| Prometheus | Low | 4–6 hours |
| Slack encryption | Medium | Migration + crypto; 1–2 days |
| Webhook retries | Medium | Celery task; 1 day |
| **Phase 2 Total** | **Medium** | **~3–4 weeks** |

---

## Phase 3 — Enterprise Features

**Goal:** RBAC, audit logs, SSO, and compliance-ready security.  
**Timeline:** 4–6 weeks  
**Complexity:** Medium–High

### Features

| Feature | Description |
|---------|-------------|
| RBAC enforcement | Role checks on all team-scoped endpoints |
| Audit log coverage | Log team create, API key, integration, budget, user invite |
| Slack webhook encryption | (From Phase 2) |
| SAML/Okta SSO | Enterprise SSO with domain allowlist |
| Team invitations | Invite by email; role assignment |
| Resource permissions | Budget edit vs view; integration connect vs view |
| MFA (optional) | TOTP for high-security orgs |

### Engineering Tasks

| Task | Description | Owner |
|------|-------------|-------|
| RBAC middleware | `require_role(owner, admin)` dependency; apply to routes | Backend |
| Route audit | Add role checks to teams, API keys, integrations, budgets | Backend |
| Audit events | `record_audit_event` for: team create, key create/rotate, integration connect, budget create/update, invite | Backend |
| SAML flow | Add `/api/v1/auth/saml/*` (metadata, ACS, SLO) | Backend |
| Okta integration | Use Okta as SAML IdP; test with Okta dev org | Backend |
| Invite flow | `POST /api/v1/teams/{id}/invites`; email with magic link | Backend |
| Invite acceptance | `GET /invite/{token}`; create TeamMember; redirect to app | Full-stack |
| Permission matrix | Document which role can do what | Docs |

### Database Changes

| Change | Type | Description |
|--------|------|-------------|
| `team_invites` | New table | `id`, `team_id`, `email`, `role`, `token`, `expires_at`, `accepted_at` |
| `oauth_identities` | Existing | Add `provider=saml` for SAML logins |
| `org_settings` | New table (optional) | `saml_entity_id`, `saml_sso_url`, `saml_x509_cert` per team |
| `audit_logs` | Existing | Ensure index on `(team_id, created_at)` for queries |

### APIs Required

| API | Method | Description |
|-----|--------|-------------|
| `POST /api/v1/auth/saml/metadata` | New | Return SP metadata for IdP config |
| `POST /api/v1/auth/saml/acs` | New | SAML Assertion Consumer Service |
| `GET /api/v1/auth/saml/slo` | New | Single Logout (optional) |
| `POST /api/v1/teams/{id}/invites` | New | Create invite; send email |
| `GET /api/v1/invite/{token}` | New | Accept invite; create membership |
| `GET /api/v1/audit-logs` | New | List audit logs (paginated, filtered by team) |
| All team-scoped routes | Modify | Add `Depends(require_role(...))` |

### UI Changes

| Page/Component | Change |
|----------------|--------|
| Settings > Authentication | Add SAML/Okta config section (entity ID, SSO URL, cert) |
| Settings > Team | Add "Invite members" button; invite form (email, role) |
| Invite acceptance | New page `/invite/[token]`; accept/decline |
| Settings > Audit | New "Audit log" tab; table with filters |
| Role-based UI | Hide edit/delete for viewer role; show for admin/owner |
| Login | Add "Sign in with SSO" when org has SAML configured |

### Estimated Complexity

| Area | Complexity | Notes |
|------|------------|-------|
| RBAC | Medium | 2–3 days |
| Audit coverage | Low | 1–2 days |
| SAML/Okta | High | 2–3 weeks |
| Invitations | Medium | 1 week |
| **Phase 3 Total** | **Medium–High** | **~4–6 weeks** |

---

## Phase 4 — Growth Features

**Goal:** Differentiation, stickiness, and expansion revenue.  
**Timeline:** 6–8 weeks  
**Complexity:** High

### Features

| Feature | Description |
|---------|-------------|
| Azure Cost Management | Third cloud provider |
| Email alerts | In addition to Slack |
| ROI/savings dashboard | Dedicated view of savings from recommendations |
| Weekly cost reports | PDF/email summary |
| Usage-based billing | Stripe metered billing for GPU-hours |
| K8s native metrics | GPU metrics from Prometheus/DCGM |
| AI cost insights | Enhanced assistant with savings suggestions |
| Recommendation actions | One-click "Apply" for right-sizing suggestions |

### Engineering Tasks

| Task | Description | Owner |
|------|-------------|-------|
| Azure integration | `integrations/providers/azure_cost_management.py` | Backend |
| Email service | SendGrid/SES; templates for alerts | Backend |
| Email alert types | Budget, anomaly, weekly digest | Backend |
| Savings dashboard | Aggregate `recommended_savings`; show vs actual | Backend + Frontend |
| Weekly report | Celery task; generate PDF; send email | Backend |
| Stripe metering | Map `usage_events` to Stripe Usage Records | Backend |
| K8s metrics | Agent or sidecar to scrape GPU metrics; store in `usage_snapshots` | Backend |
| Assistant enhancements | Prompt tuning; savings-focused responses | Backend |
| Recommendation actions | `POST /api/v1/recommendations/{id}/apply` (placeholder or webhook) | Backend |

### Database Changes

| Change | Type | Description |
|--------|------|-------------|
| `alert_settings.email_enabled` | New column | Boolean |
| `alert_settings.email_address` | New column | For digest |
| `savings_tracking` | New table (optional) | `team_id`, `date`, `recommended_savings`, `realized_savings` |
| `integration_connections` | Existing | Add `provider=azure_cost_management` |
| `usage_events` | Existing | Ensure `event_type` includes `gpu_hours` for Stripe |

### APIs Required

| API | Method | Description |
|-----|--------|-------------|
| `POST /api/v1/integrations/azure/connect` | New | Azure Cost Management connection |
| `POST /api/v1/integrations/azure/test` | New | Validate Azure credentials |
| `GET /api/v1/analytics/savings` | New | Savings over time; realized vs recommended |
| `POST /api/v1/reports/weekly` | New | Trigger weekly report generation |
| `POST /api/v1/recommendations/{id}/apply` | New | Mark as applied; optional webhook |
| `GET /api/v1/billing/usage` | Existing | Ensure returns data for Stripe metering |

### UI Changes

| Page/Component | Change |
|----------------|--------|
| Integrations | Add Azure card; connect form |
| Settings > Alerts | Add email toggle; email input for digest |
| New: Savings dashboard | `/analytics/savings` — chart of recommended vs realized savings |
| Recommendations | Add "Apply" button; confirm modal |
| Billing | Usage chart; link to Stripe metered usage |
| Assistant | Enhanced UI; savings-focused suggestions |
| Weekly report | Settings option to enable/disable; preview |

### Estimated Complexity

| Area | Complexity | Notes |
|------|------------|-------|
| Azure integration | High | 1–2 weeks |
| Email alerts | Medium | 3–5 days |
| Savings dashboard | Medium | 1 week |
| Weekly reports | Medium | 1 week |
| Stripe metering | Medium | 2–3 days |
| K8s metrics | High | 2–3 weeks |
| **Phase 4 Total** | **High** | **~6–8 weeks** |

---

## Summary Matrix

| Phase | Timeline | Complexity | Key Deliverables |
|-------|----------|------------|------------------|
| **Phase 1 — MVP** | 2–3 weeks | Low–Medium | Onboarding wizard, billing UI, empty states, Celery fix |
| **Phase 2 — SaaS Infra** | 3–4 weeks | Medium | CD, secrets, Prometheus, Slack encryption, webhook retries |
| **Phase 3 — Enterprise** | 4–6 weeks | Medium–High | RBAC, audit logs, SAML/Okta, invitations |
| **Phase 4 — Growth** | 6–8 weeks | High | Azure, email alerts, savings dashboard, Stripe metering, K8s |

---

## Dependencies Between Phases

```
Phase 1 (MVP) ──────────────────────────────────────────►
    │
    └──► Phase 2 (SaaS Infra) ─────────────────────────►
              │
              └──► Phase 3 (Enterprise) ────────────────►
                        │
                        └──► Phase 4 (Growth) ─────────►
```

- **Phase 1** can start immediately.
- **Phase 2** can overlap with Phase 1 (different owners).
- **Phase 3** should follow Phase 2 (secrets, CD in place).
- **Phase 4** can start after Phase 2; some items (e.g. Azure) are independent of Phase 3.

---

## Recommended Sprint Allocation

| Sprint | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|--------|---------|---------|---------|---------|
| 1 | Celery, env, onboarding start | — | — | — |
| 2 | Onboarding, billing UI, empty states | CD, Sentry | — | — |
| 3 | — | Prometheus, Slack encryption, retries | RBAC, audit | — |
| 4 | — | — | SAML/Okta start | — |
| 5 | — | — | SAML/Okta, invites | Email alerts |
| 6 | — | — | — | Azure, savings dashboard |
| 7–8 | — | — | — | Stripe metering, K8s, weekly reports |
