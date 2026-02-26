# SOC 2 Readiness Checklist

## Overview

This checklist maps Heliox controls to SOC 2 Trust Services Criteria (TSC) to support Type I/II audit readiness.

| Criterion | Description |
|-----------|-------------|
| **CC** | Common Criteria (security) |
| **A** | Availability |
| **PI** | Processing Integrity |
| **C** | Confidentiality |
| **PR** | Privacy (if applicable) |

---

## CC — Common Criteria (Security)

| Control ID | Control | Heliox Implementation | Status |
|------------|---------|------------------------|--------|
| CC1.1 | Commitment to integrity and ethical values | Code of conduct, security policy | ☐ Document |
| CC1.2 | Board oversight | Governance structure | ☐ Customer responsibility |
| CC2.1 | Security policies | [SECURITY_WHITEPAPER.md](./SECURITY_WHITEPAPER.md) | ☑ |
| CC2.2 | Information security roles | RBAC (owner, admin, viewer), platform admin | ☑ |
| CC3.1 | Risk assessment | Threat model, OWASP controls | ☑ |
| CC3.2 | Fraud risk | Audit log, anomaly detection | ☑ |
| CC4.1 | Quality of information | Data validation, schemas | ☑ |
| CC5.1 | Logical access | API key + JWT auth, MFA-ready | ☑ |
| CC5.2 | Prior to issuing credentials | Onboarding flow, credential delivery | ☑ |
| CC6.1 | Logical access removal | Token blacklist, API key revocation | ☑ |
| CC6.2 | Access removal procedures | [TENANT_ONBOARDING_GUIDE.md](./TENANT_ONBOARDING_GUIDE.md) | ☑ |
| CC6.6 | Encryption of sensitive data | TLS 1.2+, encryption at rest (RDS, Redis) | ☑ |
| CC6.7 | Transmission of sensitive data | HTTPS only, HSTS | ☑ |
| CC7.1 | Detection of security events | Audit log, structured logging, Sentry | ☑ |
| CC7.2 | Monitoring of system | CloudWatch, health checks | ☑ |
| CC7.3 | Evaluation of security events | [INCIDENT_RESPONSE_PLAN.md](./INCIDENT_RESPONSE_PLAN.md) | ☑ |
| CC7.4 | Response to identified incidents | Runbooks, severity levels | ☑ |
| CC8.1 | Change management | Git, CI/CD, migration versioning | ☑ |

---

## A — Availability

| Control ID | Control | Heliox Implementation | Status |
|------------|---------|------------------------|--------|
| A1.1 | Availability commitments | [SLA_TEMPLATE.md](./SLA_TEMPLATE.md) | ☑ |
| A1.2 | Capacity planning | Auto-scaling, connection pooling | ☑ |
| A2.1 | Environmental protections | AWS data center controls | ☐ AWS responsibility |
| A2.2 | System recovery | [BACKUP_RESTORE_GUIDE.md](./BACKUP_RESTORE_GUIDE.md) | ☑ |
| A2.3 | System backup | PostgreSQL, Redis backup procedures | ☑ |

---

## PI — Processing Integrity

| Control ID | Control | Heliox Implementation | Status |
|------------|---------|------------------------|--------|
| PI1.1 | Processing completeness | Idempotency, transaction handling | ☑ |
| PI1.2 | Processing accuracy | Validation, schema enforcement | ☑ |
| PI1.3 | Processing authorization | Tenant isolation, RBAC | ☑ |
| PI2.1 | System inputs | API validation, CSV ingestion checks | ☑ |
| PI2.2 | System outputs | Structured responses, error handling | ☑ |

---

## C — Confidentiality

| Control ID | Control | Heliox Implementation | Status |
|------------|---------|------------------------|--------|
| C1.1 | Confidentiality commitments | NDA, DPA templates | ☐ Customer responsibility |
| C1.2 | Confidential information identified | Cost data, credentials | ☑ |
| C2.1 | Confidential information disposal | Secure deletion, retention policy | ☐ Document |
| C2.2 | Confidential information transmission | TLS, encryption at rest | ☑ |

---

## PR — Privacy (if applicable)

| Control ID | Control | Heliox Implementation | Status |
|------------|---------|------------------------|--------|
| PR1.1 | Privacy notice | Privacy policy | ☐ Customer responsibility |
| PR2.1 | Consent for collection | Terms of service | ☐ Customer responsibility |
| PR3.1 | Collection limited to purpose | Data minimization in design | ☑ |
| PR4.1 | Retention and disposal | Retention policy | ☐ Document |
| PR5.1 | Access to personal information | User data export (if implemented) | ☐ Verify |
| PR6.1 | Disclosure to third parties | Subprocessor list | ☐ Document |
| PR7.1 | Quality of personal information | Validation, correction flows | ☑ |
| PR8.1 | Monitoring for privacy compliance | Audit log, access reviews | ☑ |

---

## Pre-Audit Actions

### Must Complete

1. **Documentation**
   - [ ] Security policy (formal document)
   - [ ] Privacy policy and retention schedule
   - [ ] Subprocessor list (AWS, Sentry, etc.)
   - [ ] Incident response contact list

2. **Technical**
   - [ ] Verify audit log retention (e.g., 1 year)
   - [ ] Confirm backup restore tested quarterly
   - [ ] API key rotation enforced for high-privilege keys
   - [ ] Feature flags for emergency kill switches

3. **Process**
   - [ ] Access review process (quarterly)
   - [ ] Vendor risk assessment for critical vendors
   - [ ] Penetration test (annual)

### Evidence to Collect

| Evidence Type | Location |
|---------------|----------|
| Audit logs | `audit_events` table, CloudWatch |
| Backup logs | RDS snapshots, backup job logs |
| Incident runbooks | [INCIDENT_RESPONSE_PLAN.md](./INCIDENT_RESPONSE_PLAN.md) |
| Architecture | [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md) |
| API documentation | [OPENAPI.md](./OPENAPI.md), `/docs` |
| Security controls | [SECURITY_WHITEPAPER.md](./SECURITY_WHITEPAPER.md) |

---

## Summary

| Category | Total | Implemented | Document | Customer |
|----------|-------|-------------|----------|----------|
| CC | 18 | 16 | 1 | 1 |
| A | 5 | 3 | 0 | 1 |
| PI | 5 | 5 | 0 | 0 |
| C | 4 | 2 | 1 | 1 |
| PR | 8 | 3 | 4 | 1 |

**Readiness:** Core security, availability, and processing integrity controls are in place. Complete remaining documentation and process items before engaging an auditor.
