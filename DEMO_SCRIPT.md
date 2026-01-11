# Heliox-AI Demo Script

## 🎯 Overview

This guide provides a complete demo workflow for Heliox-AI, showcasing the platform's cost analytics and optimization capabilities.

**Duration**: 10-15 minutes
**Audience**: Technical teams, engineering managers, finance/ops
**Goal**: Demonstrate GPU cost tracking, analytics, and AI-powered recommendations

## 🚀 Pre-Demo Setup (5 minutes)

### 1. Start Services

```bash
# From project root
cd heliox-ai

# Start backend services (FastAPI, PostgreSQL, Redis)
docker-compose up -d

# Verify services are healthy
docker-compose ps
# All services should show "Up" status

# Start frontend (in new terminal)
cd frontend
npm install  # First time only
npm run dev

# Verify frontend is running
# Open http://localhost:3000 in browser
```

### 2. Seed Demo Data

```bash
# Seed the database with mock data
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Expected response:
# {
#   "status": "success",
#   "message": "Demo data seeded successfully! 3 teams, 30 jobs, 28 cost snapshots, 69 usage snapshots created.",
#   "results": {...}
# }
```

### 3. Verify Data

```bash
# Check demo status
curl http://localhost:8000/api/v1/admin/demo/status

# Expected response:
# {
#   "environment": "dev",
#   "demo_mode_available": true,
#   "data": {
#     "teams": 3,
#     "jobs": 30,
#     "cost_snapshots": 28,
#     "usage_snapshots": 69
#   }
# }
```

## 🎬 Demo Script

### Act 1: Platform Overview (2-3 minutes)

**Opening Statement**:
> "Let me show you Heliox, a platform we built to help ML teams track and optimize their GPU infrastructure costs. In many organizations, GPU spending is growing 50-100% year-over-year, but there's limited visibility into where that money is going."

**Show**: Dashboard Homepage
- URL: http://localhost:3000
- Point out the clean, professional interface
- Note the real-time API health indicator

**Key Points**:
- Full-stack TypeScript/Python platform
- Real-time cost tracking across multiple teams and models
- Production-ready architecture

### Act 2: Cost Analytics (3-4 minutes)

#### 2.1 Daily Spend Trends

**Show**: Line chart on dashboard
- Point to the spending trend over 14 days
- Note the visualization makes patterns immediately visible

**API Demo** (optional for technical audience):
```bash
# Show the raw data
curl "http://localhost:8000/api/v1/analytics/cost/by-model?start=2026-01-01&end=2026-01-14"
```

**Key Points**:
- Track daily GPU costs automatically
- Historical trending for budget planning
- Data sourced from cloud provider billing

#### 2.2 Cost by ML Model

**Show**: Bar chart on dashboard

**Talking Points**:
> "Here we can see cost breakdown by ML model. For example, Stable Diffusion and GPT-3.5 are our highest-cost models at ~$52K each for this period. This helps teams prioritize optimization efforts."

**Key Insights**:
- Which models consume the most resources
- Job count per model (efficiency metric)
- Guides optimization prioritization

#### 2.3 Cost by Team

**Show**: Pie chart on dashboard

**Talking Points**:
> "The platform tracks spending by team for chargeback and budget allocation. All three teams—AI Platform, Data Science, and ML Research—have roughly equal spending in this period."

**Key Insights**:
- Fair cost allocation across teams
- Budget accountability
- Helps with headcount planning

### Act 3: AI-Powered Recommendations (4-5 minutes)

**Transition**:
> "Beyond tracking, Heliox provides AI-powered recommendations to optimize costs. Let me show you what it found."

#### 3.1 Get Recommendations

**API Demo**:
```bash
# Get all recommendations
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14" \
  | python3 -m json.tool | head -100
```

**Show the response structure**:
- Total recommendations: 5
- Total potential savings: **$2,376/month**
- Severity breakdown: 2 HIGH, 3 LOW

#### 3.2 HIGH Severity: Idle GPU Detection

**Show**: First recommendation in response

**Key Points**:
```json
{
  "type": "idle_gpu",
  "title": "Idle H100 GPUs on AWS",
  "severity": "high",
  "estimated_savings_usd": 1176.0,
  "evidence": {
    "expected_usage_hours": 336.0,
    "actual_usage_hours": 0.0,
    "waste_percentage": 100.0
  }
}
```

**Talking Points**:
> "The system detected 100% idle H100 GPUs over 14 days—we're paying for 336 hours but using 0. This represents $1,176 in wasted spend. The recommendation: scale down or right-size the allocation."

**Why This Matters**:
- Immediate, actionable insight
- Clear ROI ($1,176/month savings)
- Prevents budget overruns

#### 3.3 LOW Severity: Off-Hours Scheduling

**Show**: Off-hours recommendation

**Talking Points**:
> "The system also found opportunities for off-peak scheduling. The Data Science team ran 5 jobs during business hours. Moving these to off-peak could save ~$11 through discounted pricing."

**Key Points**:
- Lower urgency but still valuable
- No infrastructure changes needed
- Simple workflow adjustment

#### 3.4 Filter by Severity

**API Demo**:
```bash
# Show only HIGH severity recommendations
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14&min_severity=high"
```

**Talking Points**:
> "You can filter by severity to focus on high-impact opportunities first."

### Act 4: Interactive API Exploration (2-3 minutes)

**For Technical Audiences Only**

#### 4.1 Swagger Documentation

**Show**: http://localhost:8000/docs

**Talking Points**:
- Complete API documentation
- Interactive testing
- Authentication built-in
- Production-ready endpoints

#### 4.2 Try an Endpoint

**Interactive Demo** in Swagger UI:
1. Navigate to `/recommendations/` endpoint
2. Click "Try it out"
3. Enter dates: 2026-01-01 to 2026-01-14
4. Execute
5. Show the response

**Key Points**:
- RESTful design
- JSON responses
- Easy integration

### Closing (1-2 minutes)

**Summary**:
> "In summary, Heliox provides three core capabilities:
> 
> 1. **Real-time cost tracking** across models, teams, and providers
> 2. **Historical analytics** with interactive visualizations
> 3. **AI-powered recommendations** that found $2,376/month in potential savings
>
> The platform is production-ready with authentication, error handling, and comprehensive logging."

**Call to Action**:
- Questions?
- Integration discussion?
- Pilot program?

## 📊 Quick Reference Commands

### Health Checks
```bash
# Backend health
curl http://localhost:8000/health

# Database health
curl http://localhost:8000/health/db

# Demo status
curl http://localhost:8000/api/v1/admin/demo/status
```

### Analytics
```bash
# Cost by model
curl "http://localhost:8000/api/v1/analytics/cost/by-model?start=2026-01-01&end=2026-01-14"

# Cost by team
curl "http://localhost:8000/api/v1/analytics/cost/by-team?start=2026-01-01&end=2026-01-14"
```

### Recommendations
```bash
# All recommendations
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14"

# High severity only
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14&min_severity=high"

# Summary only
curl "http://localhost:8000/api/v1/recommendations/summary?start_date=2026-01-01&end_date=2026-01-14"
```

### Re-seed Data (if needed)
```bash
# Reset to clean state
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

## 🎯 Key Demo Data Points

| Metric | Value |
|--------|-------|
| Teams | 3 (ai-platform, data-science, ml-research) |
| Jobs | 30 |
| ML Models | 10 (GPT-4, Claude-2, Stable Diffusion, etc.) |
| Cost Period | Jan 1-14, 2026 (14 days) |
| Total Cost | $155,693 |
| Highest Cost Model | Stable Diffusion XL ($51,923) |
| Recommendations Found | 5 |
| Potential Savings | $2,376/month |
| Highest Savings Item | Idle H100 GPUs ($1,176) |

## 🎨 Customization Tips

### Adjust Date Range
```bash
# Use different dates for variety
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-05&end_date=2026-01-10"
```

### Focus on Specific Team
The data includes three teams with different characteristics:
- **ai-platform**: 10 jobs, mixed models
- **data-science**: 10 jobs, research-focused
- **ml-research**: 10 jobs, experimental models

### Emphasize Different Metrics
- **For Finance**: Focus on cost tracking and chargeback
- **For Engineering**: Focus on technical architecture and API
- **For Ops**: Focus on recommendations and optimization

## 🐛 Troubleshooting

### Frontend Not Loading
```bash
# Check if backend is running
curl http://localhost:8000/health

# Restart frontend
cd frontend
npm run dev
```

### No Data in Dashboard
```bash
# Re-seed the database
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Verify data
curl http://localhost:8000/api/v1/admin/demo/status
```

### API Returns Empty Results
```bash
# Check date range matches seeded data (Jan 1-14, 2026)
# Verify services are healthy
docker-compose ps
```

### Demo Seed Fails
```bash
# Check ENV is set to 'dev'
docker-compose exec api python -c "from app.core.config import get_settings; print(get_settings().ENV)"

# Check API key is correct
# Default: heliox-admin-key-change-in-production
```

## 📝 Demo Variations

### Short Demo (5 minutes)
1. Show dashboard (1 min)
2. Highlight one recommendation (2 min)
3. Show potential savings (1 min)
4. Q&A (1 min)

### Technical Deep Dive (20 minutes)
1. Architecture overview (3 min)
2. API exploration in Swagger (5 min)
3. Database schema review (3 min)
4. Recommendation engine logic (5 min)
5. Integration discussion (4 min)

### Executive Demo (10 minutes)
1. Problem statement (2 min)
2. Dashboard walkthrough (4 min)
3. ROI calculation ($2,376/month) (2 min)
4. Next steps (2 min)

## 🚀 Post-Demo Follow-Up

After the demo, provide:

1. **Access to Documentation**
   - Link to README.md
   - Link to API docs (Swagger)
   - Architecture diagrams

2. **Sample Integration Code**
   - Python client example
   - JavaScript/TypeScript fetch example

3. **Deployment Guide**
   - Docker Compose setup
   - Environment variables
   - Database migration steps

4. **Roadmap Discussion**
   - V2 features (ML-based forecasting, auto-remediation)
   - Custom integrations (Slack, email alerts)
   - Multi-cloud support (AWS, GCP, Azure)

---

**Ready to Demo!** 🎉

For questions or issues, check the main README.md or contact the development team.

