# Heliox-AI Design Partner Demo Guide

**Duration:** 15-20 minutes  
**Audience:** Design partners, potential customers, stakeholders  
**Goal:** Showcase GPU cost analytics, forecasting, and optimization recommendations

---

## 🚀 Quick Setup (5 minutes)

### Option 1: Automated Setup (Recommended)

```bash
# From project root
make demo
```

This will:
- ✅ Start Docker services (PostgreSQL, Redis, API)
- ✅ Apply database migrations
- ✅ Seed demo data (3 teams, 30+ jobs, cost snapshots)
- ✅ Verify all services are healthy

### Option 2: Manual Setup

```bash
# 1. Start Docker services
docker-compose up -d

# 2. Wait for services to be ready (30-60 seconds)
docker-compose ps

# 3. Run migrations
docker-compose exec api alembic upgrade head

# 4. Seed demo data
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

### Start Frontend (if not already running)

```bash
cd frontend
npm install  # First time only
npm run dev
```

The frontend will be available at: **http://localhost:3000**

---

## 📋 Demo Flow

### 1. Landing Page (2 minutes)

**Navigate to:** http://localhost:3000/landing

**What to Show:**
- Professional landing page with hero section
- Problem statement: GPU costs are unpredictable and hard to optimize
- Solution overview: Heliox provides cost analytics and optimization
- Features overview
- Pricing preview (optional)

**What to Click:**
- Scroll through the page to show all sections
- Fill out the waitlist form (use test data):
  - Name: "John Doe"
  - Email: "john@example.com"
  - Company: "Acme Corp"
  - Role: "Engineering Manager"
- Click "Join Waitlist" button
- Show success message

**Sample Questions to Ask:**
- "What's your current process for tracking GPU costs?"
- "How do you currently identify cost optimization opportunities?"
- "What would be most valuable to you: cost visibility, forecasting, or recommendations?"

---

### 2. Dashboard Overview (3-4 minutes)

**Navigate to:** http://localhost:3000 (or click "Dashboard" from header)

**What to Show:**
- Date range picker (default: last 14 days)
- Health status indicator (green = API connected)
- Daily spend trend chart
- Cost by ML Model chart
- Cost by Team pie chart
- Forecast card (bottom of page)

**What to Click:**
1. **Date Range Picker:**
   - Change the date range to "Last 30 days"
   - Show how charts update
   - Change to a custom range (e.g., last 7 days)

2. **Spend Trend Chart:**
   - Point out the daily spend patterns
   - Highlight any spikes or trends
   - Explain: "This shows your daily GPU spend over time"

3. **Cost by Model Chart:**
   - Identify top-spending models (e.g., GPT-4, LLaMA)
   - Explain: "This breaks down costs by ML model, helping you see which models consume the most budget"

4. **Cost by Team Chart:**
   - Show team distribution (e.g., Research, Production, Training)
   - Explain: "This helps you allocate costs across teams"

5. **Forecast Card:**
   - Scroll down to see the forecast section
   - Point out historical vs. forecasted spend
   - Show the horizon selector (7, 14, 30 days)
   - Explain: "This predicts future spend based on historical patterns"

**Sample Questions to Ask:**
- "Which chart is most useful for your team?"
- "How often would you check this dashboard?"
- "What insights are you hoping to get from cost forecasting?"
- "Do you currently track costs by team? How?"

---

### 3. Recommendations Page (5-6 minutes)

**Navigate to:** Click "Recommendations" button in the header (or go to http://localhost:3000/recommendations)

**What to Show:**
- List of cost optimization recommendations
- Severity indicators (High, Medium, Low)
- Filter controls (severity, type)
- Estimated savings for each recommendation
- Export to CSV functionality

**What to Click:**

1. **View All Recommendations:**
   - Show the full list (should see 10-20+ recommendations)
   - Explain: "These are AI-powered recommendations based on your actual usage data"

2. **Severity Filter:**
   - Click "High" severity chip
   - Show only high-priority recommendations
   - Explain: "High severity means immediate action could save significant money"
   - Click "All" to show all recommendations again

3. **Individual Recommendation:**
   - Click on a high-severity recommendation to expand details
   - Show:
     - Title and description
     - Estimated savings (e.g., "$1,234.56")
     - Evidence (job IDs, dates, GPU types)
     - Severity badge
   - Explain: "Each recommendation includes specific evidence from your jobs"

4. **Example High-Severity Recommendations to Highlight:**
   - **Idle GPU Spend:** "GPU instances running but not processing jobs"
   - **Over-provisioned Resources:** "Jobs using more GPU time than needed"
   - **Inefficient Models:** "Models with high cost per inference"

5. **Export Feature:**
   - Click "Export CSV" button
   - Explain: "You can export all recommendations for analysis or sharing with your team"
   - (Note: CSV will download to browser's download folder)

6. **Refresh Data:**
   - Click "Refresh" button to show data is live
   - Explain: "Recommendations update as new data is ingested"

**Sample Questions to Ask:**
- "Which type of recommendation would be most actionable for your team?"
- "How would you prioritize these recommendations?"
- "Would you want to integrate these recommendations into your workflow?"
- "What's your process for reviewing and implementing cost optimizations?"
- "How much time do you currently spend analyzing cost data?"

---

### 4. Forecast Deep Dive (2-3 minutes)

**Navigate to:** Scroll down on dashboard or go back to http://localhost:3000

**What to Show:**
- Forecast card with historical and predicted spend
- Confidence bands (shaded area around forecast)
- Horizon selection (7, 14, 30 days)

**What to Click:**
1. **Change Forecast Horizon:**
   - Click "30 days" horizon
   - Show how forecast extends further
   - Explain: "Longer horizons help with quarterly planning"
   - Change back to "14 days"

2. **Point Out Confidence Bands:**
   - Explain: "The shaded area shows the 95% confidence interval"
   - "Wider bands indicate more uncertainty in the forecast"

3. **Historical vs. Forecast:**
   - Point to the transition line (past vs. future)
   - Explain: "Historical data is solid line, forecast is dashed"

**Sample Questions to Ask:**
- "How do you currently forecast infrastructure costs?"
- "What time horizon is most useful for your planning (weekly, monthly, quarterly)?"
- "How accurate do your current forecasts need to be?"
- "Would forecasting help with budget allocation decisions?"

---

### 5. API Documentation (Optional - 2 minutes)

**Navigate to:** http://localhost:8000/docs

**What to Show:**
- Interactive API documentation (Swagger UI)
- Available endpoints
- Request/response examples

**What to Click:**
- Expand an endpoint (e.g., `/api/v1/recommendations`)
- Show the "Try it out" feature
- Explain: "Everything you see in the UI is backed by REST APIs that can be integrated"

**Sample Questions to Ask:**
- "Do you have existing cost tracking systems we'd need to integrate with?"
- "Would you want to build custom dashboards using our APIs?"
- "What other tools would you want to connect (Slack, PagerDuty, etc.)?"

---

## 🎯 Key Talking Points

### Value Propositions

1. **Cost Visibility:**
   - "Heliox gives you real-time visibility into GPU costs across teams, models, and providers"
   - "No more manual spreadsheet tracking or waiting for monthly cloud bills"

2. **AI-Powered Insights:**
   - "Our recommendation engine analyzes your actual usage patterns to identify savings opportunities"
   - "Each recommendation includes evidence from your jobs, not generic best practices"

3. **Forecasting:**
   - "Predict future spend based on historical patterns"
   - "Plan budgets with confidence intervals, not just point estimates"

4. **Actionable Recommendations:**
   - "Prioritized by severity and potential savings"
   - "Evidence-backed recommendations you can act on immediately"

### Use Cases

- **Engineering Managers:** Track team spend, identify optimization opportunities
- **Finance/Operations:** Forecast costs, allocate budgets, ROI analysis
- **ML Engineers:** Understand model costs, optimize resource usage
- **Platform Teams:** Monitor infrastructure spend, capacity planning

---

## 📊 Demo Data Overview

The seeded demo data includes:

- **3 Teams:** Research, Production, Training
- **30+ Jobs:** Mix of successful, failed, and idle jobs
- **28 Cost Snapshots:** Daily cost data over ~4 weeks
- **69 Usage Snapshots:** GPU usage patterns
- **Multiple Models:** GPT-4, LLaMA, BERT, etc.
- **Multiple Providers:** AWS, GCP, Azure
- **Multiple GPU Types:** A100, H100, V100

This creates realistic scenarios for:
- Idle GPU spend (jobs running but not processing)
- Over-provisioned resources
- Cost spikes and trends
- Team cost allocation

---

## 🔧 Troubleshooting

### Services Not Starting

```bash
# Check Docker status
docker-compose ps

# View logs
docker-compose logs api
docker-compose logs postgres

# Restart services
docker-compose restart
```

### Frontend Not Loading

```bash
# Check if frontend is running
curl http://localhost:3000

# Check if backend is accessible
curl http://localhost:8000/health

# Verify API URL in frontend
# Should default to http://localhost:8000
```

### No Data Showing

```bash
# Verify demo data was seeded
curl http://localhost:8000/api/v1/admin/demo/status

# Re-seed data if needed
curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
  -H "X-API-Key: heliox-admin-key-change-in-production"
```

### API Errors

```bash
# Check API logs
docker-compose logs -f api

# Verify database connection
docker-compose exec api python -c "from app.core.db import check_db_connection; print(check_db_connection())"
```

---

## ✅ Post-Demo Checklist

After the demo:

1. **Gather Feedback:**
   - Which features were most valuable?
   - What's missing?
   - What questions did they have?

2. **Next Steps:**
   - Schedule follow-up if interested
   - Share access to demo environment (if applicable)
   - Provide pricing/onboarding information

3. **Cleanup (Optional):**
   ```bash
   # Stop services
   docker-compose down
   
   # Or reset data for next demo
   curl -X POST http://localhost:8000/api/v1/admin/demo/seed \
     -H "X-API-Key: heliox-admin-key-change-in-production"
   ```

---

## 📝 Notes for Presenters

- **Pace:** Don't rush through features. Let users explore and ask questions
- **Customization:** Adjust the flow based on the audience (technical vs. business)
- **Pain Points:** Listen for pain points they mention and connect them to Heliox features
- **Competition:** Be prepared to compare to existing solutions (Datadog, CloudWatch, etc.)
- **Integration:** Ask about their current stack and discuss integration possibilities

---

## 🎓 Demo Script Template

**Opening (1 min):**
"Today I'm going to show you Heliox, a platform for GPU cost analytics and optimization. We'll look at cost visibility, forecasting, and AI-powered recommendations. Let's start with the dashboard."

**Dashboard (3-4 min):**
"Here's your cost dashboard. You can see daily spend trends, costs by model and team, and a forecast. What questions do you have about your current cost tracking?"

**Recommendations (5-6 min):**
"Now let's look at recommendations. These are AI-powered suggestions based on your actual usage. You can filter by severity and see specific evidence. Which recommendations would be most actionable for you?"

**Forecast (2-3 min):**
"Finally, here's the forecast. It predicts future spend with confidence intervals. How do you currently forecast infrastructure costs?"

**Closing (1 min):**
"Any questions? Would you like to explore any feature in more detail?"

---

**Last Updated:** 2026-01-10  
**Version:** 1.0
