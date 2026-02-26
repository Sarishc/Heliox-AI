# Heliox Enterprise Documentation Package

This package contains enterprise-ready documentation and operational guides for Heliox SaaS handover.

## Contents

| Document | Description |
|----------|-------------|
| [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) | High-level architecture, components, data flow, AWS deployment |
| [OPENAPI.md](./OPENAPI.md) | API documentation, `/docs`, `/redoc`, client generation |
| [TENANT_ONBOARDING_GUIDE.md](./TENANT_ONBOARDING_GUIDE.md) | Admin onboarding flow, credential delivery, verification |
| [SECURITY_WHITEPAPER.md](./SECURITY_WHITEPAPER.md) | Auth, multi-tenant isolation, OWASP controls, audit |
| [BACKUP_RESTORE_GUIDE.md](./BACKUP_RESTORE_GUIDE.md) | PostgreSQL and Redis backup/restore procedures |
| [INCIDENT_RESPONSE_PLAN.md](./INCIDENT_RESPONSE_PLAN.md) | Severity levels, phases, runbooks |
| [SLA_TEMPLATE.md](./SLA_TEMPLATE.md) | Availability tiers, performance targets, support, credits |
| [SOC2_READINESS_CHECKLIST.md](./SOC2_READINESS_CHECKLIST.md) | SOC 2 Trust Services Criteria mapping, pre-audit actions |

## Enterprise Features

- **API Key Rotation** — `POST /api/v1/admin/teams/{team_id}/api-keys/{key_id}/rotate`
- **Usage Analytics** — `GET /api/v1/admin/analytics/usage` (admin)
- **Feature Flags** — `GET /api/v1/admin/feature-flags` (admin), env `FEATURE_FLAGS`
- **Audit Log** — Team-scoped events (api_key_created, api_key_rotated, etc.)

## Handover Checklist

1. Review all documents in this package
2. Complete SOC2 pre-audit actions (see [SOC2_READINESS_CHECKLIST.md](./SOC2_READINESS_CHECKLIST.md))
3. Configure `FEATURE_FLAGS` and `ADMIN_API_KEY` (or platform admin)
4. Validate backup/restore procedure
5. Run incident response drill
6. Provide tenant onboarding runbook to ops

## Support

For enterprise support, refer to the SLA template and incident response plan for escalation paths.
