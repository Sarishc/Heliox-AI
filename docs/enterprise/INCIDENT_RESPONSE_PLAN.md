# Heliox Incident Response Plan

## Severity Levels

| Level | Description | Example |
|-------|-------------|---------|
| **P0** | Complete outage | API down, data loss |
| **P1** | Major degradation | 50%+ errors, critical feature broken |
| **P2** | Minor degradation | Slow responses, non-critical bug |
| **P3** | Low impact | Cosmetic, workaround exists |

## Response Phases

### 1. Detection & Triage (0–15 min)

- **Alerts:** CloudWatch, Sentry, PagerDuty
- **Verify:** Reproduce or confirm incident
- **Severity:** Assign P0–P3
- **Communicate:** Page on-call, create incident channel

### 2. Containment (15–60 min)

- **P0/P1:** Consider rollback, scale up, or disable feature
- **Mitigation:** Rate limit abuse, block bad actor, revert deploy
- **Status page:** Update if customer-facing

### 3. Resolution (1–4 hours)

- **Root cause:** Logs, traces, recent changes
- **Fix:** Deploy patch, config change, or data fix
- **Verify:** Smoke tests, monitoring green

### 4. Post-Incident (24–48 hours)

- **Postmortem:** Timeline, root cause, action items
- **Blameless:** Focus on process, not individuals
- **Follow-up:** Implement preventive measures

## Runbooks

### API 5xx Spike

1. Check CloudWatch 5xx alarm
2. Review Sentry for exceptions
3. Check DB connection pool, Redis
4. Rollback last deploy if correlated
5. Scale ECS tasks if resource-bound

### Database Connection Exhaustion

1. Check `pool_size` and `max_overflow`
2. Identify long-running queries (slow query log)
3. Restart API to reset pool (short-term)
4. Increase pool or add read replicas (long-term)

### Suspected Data Breach

1. **Immediate:** Revoke suspected API keys, disable accounts
2. **Forensics:** Audit log review, access patterns
3. **Legal:** Engage legal/compliance per policy
4. **Notification:** Per regulatory requirements (e.g., GDPR 72h)

## Contacts

| Role | Contact |
|------|---------|
| On-call engineer | PagerDuty / rotation |
| Security lead | security@company.com |
| Customer success | cs@company.com |
