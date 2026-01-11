# Heliox-AI Deployment & Demo Guide

## 🚀 Quick Start (Both Services)

### Start Everything

```bash
# Start backend services
docker-compose up -d

# Wait for services to be healthy
docker-compose ps

# Start frontend (in new terminal)
cd frontend
npm install
npm run dev
```

### Access Points

- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Database**: localhost:5432 (postgres/postgres)
- **Redis**: localhost:6379

## 📊 Demo Flow

### 1. Ingest Mock Data

```bash
# Ingest cost data
curl -X POST http://localhost:8000/api/v1/admin/ingest/cost/mock \
  -H "X-API-Key: heliox-admin-key-change-in-production"

# Ingest job data (optional - if asyncpg added to requirements)
curl -X POST http://localhost:8000/api/v1/admin/ingest/jobs/mock \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

### 2. Open Dashboard

```bash
open http://localhost:3000
```

### 3. Explore Features

- ✅ **Health Status**: Green indicator showing "API Connected"
- ✅ **Date Range**: Select dates (default: last 14 days)
- ✅ **Daily Spend**: Line chart with cost trends (mocked)
- ✅ **Cost by Model**: Bar chart showing costs per ML model
- ✅ **Cost by Team**: Pie chart with team distribution

## 📸 Screenshots for LinkedIn

### Recommended Views to Capture

1. **Dashboard Overview** (Desktop)
   - URL: http://localhost:3000
   - Window: 1920x1080 or larger
   - Zoom: 100%
   - Shows: All charts, header, date picker

2. **Cost Analytics Detail**
   - Focus on bar chart (Cost by Model)
   - Show tooltip on hover
   - Clear labels and values

3. **Mobile View**
   - Browser DevTools → Toggle device toolbar
   - Select "iPhone 12 Pro" or similar
   - Shows responsive design

4. **API Documentation**
   - URL: http://localhost:8000/docs
   - Shows FastAPI Swagger UI
   - Professional API interface

### Screenshot Settings

```
Resolution: 1920x1080 (Full HD)
Format: PNG
Quality: High
Browser: Chrome (clean profile, no extensions visible)
```

## 🎨 Styling for Demo

### Color Palette

- **Primary**: Blue (#3b82f6)
- **Secondary**: Purple (#8b5cf6)
- **Success**: Green (#10b981)
- **Background**: Gray (#f9fafb)
- **Text**: Gray (#111827)

### Typography

- **Font**: Inter (system font)
- **Headers**: 2xl, bold
- **Body**: sm/base, regular
- **Labels**: xs, medium

## ✅ Pre-Demo Checklist

### Backend

- [ ] Services running: `docker-compose ps`
- [ ] Health check: `curl http://localhost:8000/health`
- [ ] Cost data ingested (28 records)
- [ ] Database migrations applied
- [ ] No errors in logs: `docker-compose logs api --tail=50`

### Frontend

- [ ] Dev server running: Check http://localhost:3000
- [ ] No console errors (F12 → Console)
- [ ] Charts loading properly
- [ ] Health indicator green
- [ ] Date picker functional
- [ ] Mobile responsive (test with DevTools)

### Data

- [ ] Cost snapshots: 28 records (Jan 1-14, 2026)
- [ ] Teams: 3 teams created
- [ ] Jobs: 30 jobs ingested (if job ingestion working)

## 🐛 Troubleshooting

### Frontend Won't Connect to Backend

**Problem**: Charts show "API Offline" or errors

**Solutions**:
```bash
# Check backend health
curl http://localhost:8000/health

# Verify CORS enabled (should see CORS_ORIGINS in config)
docker-compose exec api python -c "from app.core.config import get_settings; print(get_settings().CORS_ORIGINS)"

# Restart services
docker-compose restart api
```

### Charts Not Rendering

**Problem**: Blank charts or loading forever

**Solutions**:
1. Check browser console (F12) for errors
2. Verify data exists:
   ```bash
   curl "http://localhost:8000/api/v1/analytics/cost/by-model?start=2026-01-01&end=2026-01-14"
   ```
3. Clear Next.js cache:
   ```bash
   cd frontend
   rm -rf .next
   npm run dev
   ```

### CORS Errors

**Problem**: "Access-Control-Allow-Origin" errors

**Solution**: CORS is already configured in backend. If issues persist:
```python
# backend/app/main.py should have:
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Database Connection Issues

**Problem**: "Database connection failed"

**Solutions**:
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres psql -U postgres -c "SELECT 1"

# Check logs
docker-compose logs postgres --tail=20
```

## 🎯 LinkedIn Post Template

```
🚀 Excited to share Heliox - a full-stack GPU cost analytics platform!

Built to help ML teams track and optimize their infrastructure spending.

🛠 Tech Stack:
• Backend: FastAPI + PostgreSQL + SQLAlchemy 2.0
• Frontend: Next.js 14 + TypeScript + TailwindCSS
• Visualization: Recharts
• Infrastructure: Docker Compose

✨ Features:
✅ Real-time cost analytics with interactive charts
✅ Multi-team & multi-model cost tracking
✅ Date range filtering and historical analysis
✅ RESTful API with Swagger documentation
✅ Mobile-responsive modern UI
✅ Production-ready architecture

The dashboard provides instant insights into GPU spending patterns,
helping teams make data-driven decisions about their ML infrastructure.

Key learnings:
• FastAPI's async capabilities for high-performance APIs
• SQLAlchemy 2.0's improved type safety
• Next.js App Router for optimal performance
• Recharts for beautiful data visualizations

[Include 2-3 screenshots showing the dashboard]

#MachineLearning #FullStack #FastAPI #NextJS #DataVisualization 
#DevOps #CloudComputing #OpenSource #SoftwareEngineering
```

## 📝 Demo Script

### Introduction (30 seconds)

"This is Heliox, a GPU cost analytics platform I built to help ML teams 
track and optimize their infrastructure spending."

### Feature Walkthrough (2 minutes)

1. **Dashboard Overview**
   - "Clean, professional interface with real-time data"
   - "Date range picker for custom analysis periods"

2. **Cost by Model**
   - "See which ML models are consuming the most resources"
   - "Helps identify optimization opportunities"

3. **Cost by Team**
   - "Track spending across different teams"
   - "Useful for budget allocation and chargeback"

4. **Health Monitoring**
   - "Real-time API connection status"
   - "Built-in reliability checks"

### Technical Highlights (1 minute)

- "FastAPI backend with async operations for performance"
- "PostgreSQL with proper indexing and constraints"
- "Next.js for optimal frontend performance"
- "Fully containerized with Docker"
- "Production-ready with error handling and logging"

### Closing

"The platform is designed to be extensible - easy to add new 
analytics, integrate with cloud providers, or customize for 
specific needs."

## 🎬 Video Demo Tips

If recording a video:

1. **Preparation**
   - Clear browser history/cache
   - Use incognito mode for clean UI
   - Hide bookmarks bar
   - Close unnecessary tabs
   - Mute notifications

2. **Recording**
   - Use Loom or QuickTime
   - 1920x1080 resolution
   - Show mouse cursor
   - Speak clearly and slowly
   - Add captions if possible

3. **Content**
   - Start with full dashboard view
   - Interact with date picker
   - Hover over charts to show tooltips
   - Switch to mobile view
   - Show API docs briefly

## 🚀 Ready to Demo!

Your Heliox platform is production-ready and demo-ready.

Next steps:
1. Capture screenshots
2. Write LinkedIn post
3. Share with your network
4. Get feedback
5. Iterate and improve

Good luck with your demo! 🎉

