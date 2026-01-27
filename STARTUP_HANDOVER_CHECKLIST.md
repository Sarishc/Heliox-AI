# Heliox Startup Handover Checklist

Use this checklist when handing off Heliox to a new startup customer.

---

## Pre-Handover (You Complete)

- [x] ✅ **Code audit completed** - See `PRODUCTION_READINESS_AUDIT.md`
- [x] ✅ **Critical bugs fixed**:
  - [x] Celery Beat permission error
  - [x] Database schema migration issues
  - [x] Missing API library file
  - [x] BusinessEfficiencyResponse schema
  - [x] Budget tables created
- [x] ✅ **Demo data seeded**
- [x] ✅ **Production configs created**:
  - [x] `docker-compose.prod.yml`
  - [x] `.env.local.example` for frontend
  - [x] `DEPLOYMENT_GUIDE.md`

---

## Day 1: Initial Handover

### What to Send the Startup:

1. **GitHub Repository Access**
   - Add their GitHub username as collaborator
   - Send: Repository URL

2. **Credentials File** (encrypted)
   ```
   ADMIN_API_KEY=<generated_secure_key>
   SECRET_KEY=<generated_secure_key>
   DATABASE_URL=<if_using_shared_instance>
   ```

3. **Documentation Links**:
   - Main README: `/README.md`
   - Quick Start: `/docs/QUICKSTART.md`
   - Deployment Guide: `/DEPLOYMENT_GUIDE.md`
   - Production Audit: `/PRODUCTION_READINESS_AUDIT.md`

4. **Demo Credentials** (if providing demo instance):
   ```
   Dashboard: https://demo.heliox.ai
   Email: demo@yourstartup.com
   Password: <secure_password>
   API Key: <demo_api_key>
   ```

### Onboarding Call (30 minutes):

**Agenda**:
1. (5 min) Architecture overview
2. (10 min) Walk through dashboard features
3. (10 min) API integration demo (show curl examples)
4. (5 min) Answer questions

**Screen Share**:
- Show: Dashboard with live data
- Show: API docs at `/docs`
- Show: How to create budget policies
- Show: How to ingest cost data via API

---

## Week 1: Startup Self-Service Setup

### Startup Completes:

- [ ] **Clone repository**
  ```bash
  git clone https://github.com/yourorg/heliox.git
  cd heliox
  ```

- [ ] **Choose deployment platform**
  - Recommended: Railway (easiest)
  - Alternative: Vercel + Render, AWS ECS

- [ ] **Generate credentials**
  ```bash
  openssl rand -base64 32  # SECRET_KEY
  openssl rand -base64 32  # ADMIN_API_KEY
  # Save in password manager!
  ```

- [ ] **Deploy backend** (follow `/DEPLOYMENT_GUIDE.md`)

- [ ] **Deploy frontend** (Vercel/Railway)

- [ ] **Run database migrations**
  ```bash
  railway run alembic upgrade head
  # or
  docker-compose exec api alembic upgrade head
  ```

- [ ] **Create first team**
  ```bash
  curl -X POST https://api.yourdomain.com/api/v1/admin/onboard \
    -H "X-API-Key: $ADMIN_API_KEY" \
    -d '{"team_name":"Acme Corp","api_key_name":"Prod","monthly_budget_usd":25000}'
  ```

- [ ] **Test data ingestion**
  ```bash
  # Use API key from onboarding response
  curl -X POST https://api.yourdomain.com/api/v1/ingest/cost \
    -H "X-API-Key: $API_KEY" \
    -d '{"records":[{"date":"2026-01-01","provider":"aws","gpu_type":"a100","cost_usd":1000}]}'
  ```

- [ ] **Verify dashboard loads**
  - Visit frontend URL
  - See cost data appearing

---

## Week 2: Integration & Customization

### Startup Integrates:

- [ ] **Deploy Heliox agent** on GPU infrastructure
  ```bash
  # Option 1: Python agent (recommended)
  python agent/heliox_agent.py \
    --endpoint https://api.yourdomain.com \
    --api-key $API_KEY \
    --interval 300  # Send data every 5 minutes
  
  # Option 2: Kubernetes DaemonSet
  kubectl apply -f agent/k8s-daemonset.yaml
  ```

- [ ] **Connect cost data sources**
  - AWS Cost Explorer API
  - GCP Billing API
  - Azure Cost Management API

- [ ] **Ingest business metrics**
  ```bash
  curl -X POST https://api.yourdomain.com/api/v1/analytics/business-metrics \
    -H "X-API-Key: $API_KEY" \
    -d '{"metrics":[{"date":"2026-01-01","revenue_usd":5000,"active_users":100,"requests":10000}]}'
  ```

- [ ] **Configure Slack alerts**
  ```bash
  curl -X POST https://api.yourdomain.com/api/v1/alerts/webhook \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -d '{"slack_webhook_url":"https://hooks.slack.com/services/..."}'
  ```

- [ ] **Set up budget policies**
  ```bash
  curl -X POST https://api.yourdomain.com/api/v1/budgets \
    -H "X-API-Key: $API_KEY" \
    -d '{"environment":"prod","monthly_budget_usd":10000,"alert_thresholds":[0.7,0.9]}'
  ```

---

## Ongoing Support

### What Startups Will Ask:

**Q: How do I add more team members?**
A: Currently manual. Admin must:
1. Create user account via `/api/v1/auth/register`
2. User logs in, gets access token
3. Admin creates API key for team

**Improvement Needed**: Team invitation flow (not implemented yet)

**Q: How accurate is the forecasting?**
A: 
- Uses moving average for < 30 days of data (±15% accuracy)
- Uses LightGBM for >= 30 days (±10% accuracy)
- Requires at least 7 days of historical data
- Confidence bands show uncertainty range

**Q: Can I customize the dashboard?**
A: Limited customization:
- ✅ Can filter by date range
- ✅ Can filter by environment (prod/staging/dev)
- ❌ Can't create custom dashboards (future feature)
- ❌ Can't add custom widgets (future feature)

**Q: How do I export data?**
A:
- CSV export: Via Reports page → Export CSV
- PDF export: Via Reports page → Export PDF
- API: Call analytics endpoints directly and parse JSON

**Q: Is my data secure?**
A: Yes, with caveats:
- ✅ Team data is isolated (multi-tenant)
- ✅ API keys are hashed (bcrypt)
- ✅ Passwords are hashed (bcrypt)
- ⚠️ Slack webhooks are plaintext (encrypt in future)
- ⚠️ No SOC 2 / ISO 27001 compliance yet

**Q: What happens if Heliox goes down?**
A:
- API downtime: Dashboard shows "Unable to connect" errors
- Database downtime: API returns 503 Service Unavailable
- Redis downtime: Forecasts not cached (slower), Celery stops
- Recommendation: Set up uptime monitoring and alerts

**Q: How much does it cost to run?**
A:
- Railway (hobby): $20-50/month
- Railway (scale): $70-150/month
- AWS (production): $150-500/month
- Depends on: Database size, API traffic, number of teams

---

## Red Flags to Watch For

### Signs the Startup Needs Help:

1. **Dashboard shows all 401 errors**
   - Likely: API key not set correctly
   - Fix: Verify `NEXT_PUBLIC_API_BASE_URL` and localStorage has API key

2. **Forecast shows "Not enough data"**
   - Likely: Less than 7 days of cost snapshots
   - Fix: Ingest more historical data

3. **Celery tasks not running**
   - Check: `docker logs heliox-beat` and `docker logs heliox-worker`
   - Common: Permission errors, Redis connection issues

4. **Database growing too fast**
   - Check: Number of cost snapshots (should be ~365 per year per GPU type)
   - Fix: Implement data retention policy (delete old snapshots)

5. **API responses very slow (> 5 seconds)**
   - Check: Database query performance
   - Fix: Add pagination, optimize queries, increase resources

---

## Escalation Path

### When Startup Can Self-Serve:
- ✅ Adding cost data via API
- ✅ Creating budget policies
- ✅ Viewing analytics dashboards
- ✅ Exporting reports
- ✅ Basic troubleshooting (logs, health checks)

### When Startup Needs Your Help:
- ❌ Database migration failures
- ❌ Production deployment issues
- ❌ Security incidents (API key leaks)
- ❌ Data corruption or loss
- ❌ Custom feature requests
- ❌ Integration with complex billing systems

### Support Tiers:

**Tier 1: Email Support (48-hour response)**
- Documentation questions
- API usage examples
- Dashboard navigation help

**Tier 2: Slack Support (4-hour response)**
- Deployment troubleshooting
- Configuration assistance
- Bug reports

**Tier 3: Emergency Support (1-hour response)**
- Production outages
- Data loss incidents
- Security vulnerabilities

---

## Success Metrics

### After 30 Days, Startup Should Have:

- [ ] **Active team account** with >= 1 API key
- [ ] **Cost data flowing** (>= 7 days of snapshots)
- [ ] **Budget policies configured** (at least 1)
- [ ] **Slack alerts working** (received at least 1 notification)
- [ ] **Generated 1+ reports** (CSV or PDF)
- [ ] **Dashboard used daily** (check API usage logs)

### Engagement Indicators:

**Healthy Usage** (Startup is getting value):
- Daily API calls: 100-1,000+
- Teams created: 1-3
- API keys created: 2-5
- Cost snapshots: 100-1,000+
- Reports generated: 2-10 per month

**Low Engagement** (Risk of churn):
- No API calls for 7+ days
- No new cost data in 14+ days
- No budget policies configured
- No reports generated

**Action**: Proactive check-in, offer migration help, provide training

---

## Known Limitations (Set Expectations)

### What Heliox CAN Do Today:

1. ✅ **Track GPU costs** across AWS, GCP, Azure, on-prem
2. ✅ **Forecast spend** (7-30 day horizons)
3. ✅ **Detect anomalies** (unusual cost spikes)
4. ✅ **Budget alerts** (Slack notifications on threshold breach)
5. ✅ **Multi-tenant isolation** (teams can't see each other's data)
6. ✅ **Cost breakdown** by model, team, GPU type, provider
7. ✅ **Recommendations** for cost optimization
8. ✅ **Reports** (CSV, PDF export with share links)

### What Heliox CANNOT Do Yet:

1. ❌ **Real-time cost tracking** (daily granularity only)
2. ❌ **Custom dashboards** (fixed widgets only)
3. ❌ **Team member roles** (all users have full access)
4. ❌ **SSO integration** (email/password only)
5. ❌ **Advanced ML forecasting** (simple models only)
6. ❌ **Cost allocation tags** (no AWS/GCP tag propagation)
7. ❌ **Email alerts** (Slack only)
8. ❌ **Audit logs** (basic logging only, no UI)
9. ❌ **Data retention policies** (data stored indefinitely)
10. ❌ **White-label branding** (Heliox branding baked in)

### Roadmap for Missing Features:

**Q2 2026**:
- Team member roles (RBAC)
- Email notifications
- Custom dashboards

**Q3 2026**:
- SSO integration (Google, Okta)
- Advanced forecasting (Prophet, LSTM)
- Cost allocation tags

**Q4 2026**:
- Real-time cost tracking
- White-label option
- SOC 2 compliance

---

## Final Handover Steps

### Before You Leave:

1. **Document any custom changes** you made for this specific startup
2. **Save all credentials** in shared password manager (1Password, LastPass)
3. **Transfer domain ownership** (if you registered it)
4. **Grant admin access** to their technical co-founder
5. **Schedule 30-day check-in** to ensure everything is running smoothly

### Hand Over to Startup:

1. **Access**:
   - GitHub repo collaborator access
   - Production API admin key
   - Database credentials (if self-hosted)
   - Vercel/Railway dashboard access

2. **Documentation**:
   - All `.md` files in repository
   - Custom deployment notes (if any)
   - Troubleshooting runbook

3. **Monitoring**:
   - Sentry account (if set up)
   - Uptime monitor access
   - Log aggregation access (if set up)

---

## Emergency Contact Info

**If Production Goes Down**:

1. **Check health endpoint**: `curl https://api.yourdomain.com/health`
2. **Check service status**: Railway/AWS dashboard
3. **Check logs**: `docker logs heliox-api --tail 100`
4. **Restart services**: `docker-compose restart` or restart via dashboard
5. **Contact support**: support@heliox.ai (if escalation needed)

**Common Fixes**:
- **API down**: Restart API container
- **Database connection error**: Check DATABASE_URL, restart database
- **Out of memory**: Increase container resources
- **Slow queries**: Add database indexes (contact support)

---

## Post-Handover Support Plan

### Week 1-2: Active Monitoring
- Daily check-in on Slack
- Review logs for errors
- Monitor API usage patterns
- Quick fixes for minor issues

### Week 3-4: Passive Monitoring
- Every 2-3 days check-in
- Review weekly usage report
- Address major issues only

### Month 2+: On-Demand Support
- Respond to support tickets
- Monthly usage review (optional)
- Feature requests discussion

---

## SLA Expectations (Set with Startup)

### Response Times:
- **Critical (production down)**: 1-2 hours
- **High (feature broken)**: 4-8 hours
- **Medium (questions)**: 24 hours
- **Low (feature requests)**: Best effort

### Uptime Target:
- **Development**: No SLA (best effort)
- **Production**: 99.5% (3.6 hours downtime/month acceptable)
- **Enterprise**: 99.9% (43 minutes downtime/month)

### Maintenance Windows:
- **Scheduled**: Sundays 2-4 AM EST
- **Emergency**: Anytime (with notification)

---

## Handover Sign-Off

**Startup Confirms**:
- [ ] I can access the GitHub repository
- [ ] I can deploy to my chosen platform (Railway/AWS/GCP)
- [ ] I can log into the dashboard
- [ ] I can call APIs with my API key
- [ ] I understand the limitations and roadmap
- [ ] I know how to contact support for issues

**You Confirm**:
- [ ] All critical bugs are fixed
- [ ] Demo data is seeded and visible
- [ ] Documentation is up-to-date
- [ ] Credentials are securely transferred
- [ ] Monitoring is set up (Sentry, uptime checks)
- [ ] Backups are configured and tested

**Signatures**:
```
Startup Technical Lead: _________________ Date: _______
Heliox Handover Engineer: _______________ Date: _______
```

---

**Congratulations! 🎉**

The startup is now ready to use Heliox for GPU cost optimization. Schedule a 30-day follow-up to ensure everything is running smoothly and gather feedback for improvements.
