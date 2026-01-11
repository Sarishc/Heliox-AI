# Heliox-AI Demo Quick Start

## 🚀 5-Minute Demo Setup

### 1. Start Services
```bash
cd heliox-ai
docker-compose up -d
cd frontend && npm run dev
```

### 2. Seed Demo Data (One Command!)
```bash
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

### 3. Open Dashboard
```bash
open http://localhost:3000
```

## ✅ What You Get

- **3 Teams**: ai-platform, data-science, ml-research
- **30 Jobs**: 10 different ML models (GPT-4, Claude-2, Stable Diffusion, etc.)
- **$155K in Costs**: 14 days of GPU spending (Jan 1-14, 2026)
- **5 Recommendations**: $2,376/month in potential savings
- **28 Cost Snapshots**: Daily cost data for A100 and H100 GPUs
- **24 Usage Snapshots**: GPU utilization metrics

## 🎬 Demo Flow (10-15 minutes)

### Act 1: Platform Overview (2-3 min)
- Show dashboard at http://localhost:3000
- Point out real-time API health indicator
- Highlight clean, professional UI

### Act 2: Cost Analytics (3-4 min)
- **Daily Spend Trend**: Line chart showing 14 days
- **Cost by Model**: Bar chart - Stable Diffusion XL is highest at $52K
- **Cost by Team**: Pie chart - roughly equal distribution

### Act 3: AI Recommendations (4-5 min)
```bash
curl "http://localhost:8000/api/v1/recommendations/?start_date=2026-01-01&end_date=2026-01-14"
```

**Key Points**:
- 2 HIGH severity: Idle H100 and A100 GPUs ($2,352 savings)
- 3 LOW severity: Off-hours scheduling ($24 savings)
- Total: $2,376/month potential savings

### Act 4: API Exploration (2-3 min)
- Open Swagger UI: http://localhost:8000/docs
- Show interactive API testing
- Demonstrate authentication

## 📊 Key Demo Talking Points

### Problem Statement
> "ML teams are spending 50-100% more on GPU infrastructure year-over-year, but have limited visibility into where that money is going."

### Solution
> "Heliox provides real-time cost tracking, analytics, and AI-powered recommendations to optimize GPU spending."

### ROI
> "In this demo environment, we identified $2,376/month in savings opportunities—that's $28K annually from just 3 teams."

### Technical Highlights
- Production-ready FastAPI backend
- Next.js frontend with TailwindCSS
- PostgreSQL + Redis for data persistence
- Docker Compose for easy deployment
- Comprehensive API documentation

## 🔧 Demo Commands

### Health Checks
```bash
curl http://localhost:8000/health
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

### Re-seed (if needed)
```bash
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

## 🎯 Demo Variations

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

## 🐛 Troubleshooting

### Frontend Not Loading
```bash
# Check if backend is running
curl http://localhost:8000/health

# Restart frontend
cd frontend && npm run dev
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
- Check date range matches seeded data (Jan 1-14, 2026)
- Verify services are healthy: `docker-compose ps`

### Demo Seed Fails
- Check ENV is set to 'dev': `docker-compose exec api env | grep ENV`
- Verify API key is correct: `heliox-admin-key-change-in-production`

## 📚 Additional Resources

- **Full Demo Script**: See `DEMO_SCRIPT.md` for detailed presentation flow
- **API Documentation**: http://localhost:8000/docs
- **Main README**: See `README.md` for architecture and setup details

## 🎊 You're Ready!

Your Heliox platform is now demo-ready. Practice the flow once, customize the talking points for your audience, and showcase your work!

**Questions?** Check `DEMO_SCRIPT.md` for more detailed guidance.

---

**Built with**: FastAPI • Next.js • PostgreSQL • Redis • Docker
**Demo Data**: 3 teams • 30 jobs • $155K costs • $2.4K savings
**Demo Time**: 10-15 minutes

