# Heliox Security Whitepaper

## Executive Summary

Heliox implements defense-in-depth security controls for multi-tenant SaaS, including authentication, authorization, data isolation, and compliance-ready practices.

## Authentication & Authorization

### API Key Security

- **Hashing:** API keys stored as SHA-256 hashes (never plaintext)
- **Constant-time comparison:** Prevents timing attacks
- **Rotation:** Supported via create-new + revoke-old workflow

### Session Security

- **httpOnly cookies:** JWT stored in httpOnly, Secure, SameSite cookies
- **Token blacklist:** Revoked tokens invalidated in Redis
- **Expiration:** Configurable token TTL

### Multi-Tenant Isolation

- **Row-level scoping:** All queries filtered by `team_id`
- **No cross-tenant access:** Tenant A cannot access Tenant B data
- **404 on missing:** Returns 404 (not 403) to avoid existence leakage

## Infrastructure Security

### Network

- **HTTPS only** in production (HSTS, redirect)
- **VPC isolation** (AWS private subnets)
- **Security groups** restrict traffic

### Data at Rest

- **Database:** PostgreSQL with encryption at rest (RDS)
- **Redis:** ElastiCache encryption
- **Secrets:** SSM Parameter Store / Secrets Manager

### Data in Transit

- **TLS 1.2+** for all connections
- **Certificate pinning** for external integrations (optional)

## Application Security

### OWASP Controls

| Control | Implementation |
|---------|----------------|
| Rate limiting | 600 req/min per client |
| Brute force | 5 attempts/min, lockout after 5 failures |
| CSRF | Double-submit cookie for cookie auth |
| XSS | CSP, X-Content-Type-Options |
| SQL injection | Parameterized queries (SQLAlchemy ORM) |

### Security Headers

- `Strict-Transport-Security`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Content-Security-Policy`

## Audit & Compliance

- **Audit log:** Team-scoped actions (api_key_created, team_onboarded, etc.)
- **Correlation IDs:** Request tracing
- **Structured logging:** JSON format, no PII in logs

## Incident Response

See [INCIDENT_RESPONSE_PLAN.md](./INCIDENT_RESPONSE_PLAN.md).
