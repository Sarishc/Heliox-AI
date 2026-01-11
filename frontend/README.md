# Heliox Frontend Dashboard

Modern, responsive dashboard for GPU cost analytics built with Next.js, TypeScript, and TailwindCSS.

## 🚀 Quick Start

### Prerequisites

- Node.js 18+ 
- npm or yarn
- Heliox backend running on `http://localhost:8000`

### Installation

```bash
# Install dependencies
npm install

# Set up environment variables
cp .env.local.example .env.local
# Edit .env.local and set NEXT_PUBLIC_API_BASE_URL if needed
```

### Development

```bash
# Run development server
npm run dev

# Open http://localhost:3000 in your browser
```

### Production Build

```bash
# Build for production
npm run build

# Start production server
npm start
```

### Vercel Deployment

The frontend is ready for deployment on Vercel.

**Deployment Steps:**

1. **Connect Repository** to Vercel
2. **Set Environment Variable:**
   - Add `NEXT_PUBLIC_API_BASE_URL` in Vercel dashboard
   - Value: Your backend API URL (e.g., `https://your-api.railway.app`)
   - **Important:** Use root URL only, not `/api/v1` path
3. **Deploy** - Vercel will auto-deploy on git push

**Production Build Verification:**
- Build should complete without errors
- No hardcoded localhost URLs in production bundle
- API calls use environment variable
- Graceful error handling if API is unreachable

## 📊 Features

### Dashboard (/)
- **Date Range Picker**: Select custom date ranges for analytics
- **Daily Spend Trend**: Line chart showing cost trends over time (mocked)
- **Cost by ML Model**: Bar chart of costs grouped by model
- **Cost by Team**: Pie chart showing team cost distribution
- **Health Status**: Real-time API connection indicator

### Components

#### DateRangePicker
Simple date inputs for selecting analysis period.

#### SpendTrendChart
Line chart showing daily spend trends. Currently uses mocked data. 
To connect to real endpoint, replace mock logic with API call to:
```
GET /analytics/cost/daily?start=YYYY-MM-DD&end=YYYY-MM-DD
```

#### CostByModelChart
Bar chart fetching from:
```
GET /analytics/cost/by-model?start=YYYY-MM-DD&end=YYYY-MM-DD
```

#### CostByTeamChart
Pie chart fetching from:
```
GET /analytics/cost/by-team?start=YYYY-MM-DD&end=YYYY-MM-DD
```

#### HealthStatus
Monitors backend health via `GET /health`

## 🎨 Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: TailwindCSS
- **Charts**: Recharts
- **Date Handling**: date-fns

## 🔧 Configuration

### Environment Variables

Create `.env.local` file for local development:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_BETA_ACCESS_CODE=your-access-code-here
```

**Variables:**
- `NEXT_PUBLIC_API_BASE_URL` - Backend API URL (root URL, e.g., `http://localhost:8000` or `https://api.example.com`)
  - API endpoints are automatically prefixed with `/api/v1/`
  - Health endpoint is at `/health` (root level)
- `NEXT_PUBLIC_BETA_ACCESS_CODE` - Optional access code for private beta
  - If not set, dashboard is open (useful for development)
  - If set, users must enter this code to access dashboard
  - Access is persisted in localStorage
  - Landing page (`/landing`) is always accessible

#### For Vercel Deployment

1. **Set Environment Variables in Vercel Dashboard:**
   - Go to your project → Settings → Environment Variables
   - Add the following variables:
   
   **Required:**
   - `NEXT_PUBLIC_API_BASE_URL` = Your backend API URL (e.g., `https://api.heliox.ai`)
   
   **Optional (for private beta):**
   - `NEXT_PUBLIC_BETA_ACCESS_CODE` = Your beta access code (e.g., `heliox-beta-2024`)
   
   - Apply to: Production, Preview, and Development (as needed)

2. **Add Custom Domains (if using custom domain):**
   - Go to Project → Settings → Domains
   - Add your custom domain(s): `heliox.ai`, `app.heliox.ai`, etc.
   - Configure DNS records as instructed by Vercel

3. **Redeploy** after adding environment variables or domains

**Example:**
```
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai
NEXT_PUBLIC_BETA_ACCESS_CODE=heliox-beta-2024
```

**Note:** If `NEXT_PUBLIC_BETA_ACCESS_CODE` is not set, the dashboard will be open (no access gate).

#### Custom Domain Setup

For custom domain deployment (e.g., `heliox.ai` and `app.heliox.ai`):

- **Backend CORS:** Must include all frontend domains in `CORS_ORIGINS`
- **Frontend Routing:** Next.js handles subdomains automatically (no configuration needed)
- **API URLs:** Use environment variables (no hardcoded URLs)
- **localStorage:** Domain-safe by default (scoped to current domain)

See `DOMAIN_DEPLOYMENT_README.md` for detailed custom domain setup guide.

### API Endpoints Expected

The dashboard connects to these backend endpoints:

1. **Health Check**
   ```
   GET /health
   Response: { "status": "ok" }
   ```

2. **Cost by Model**
   ```
   GET /analytics/cost/by-model?start=2026-01-01&end=2026-01-14
   Response: [
     {
       "model_name": "llama-2-7b",
       "total_cost_usd": 5234.56,
       "job_count": 10,
       "start_date": "2026-01-01",
       "end_date": "2026-01-14"
     }
   ]
   ```

3. **Cost by Team**
   ```
   GET /analytics/cost/by-team?start=2026-01-01&end=2026-01-14
   Response: [
     {
       "team_name": "ml-research",
       "team_id": "uuid",
       "total_cost_usd": 18500.00,
       "job_count": 25,
       "start_date": "2026-01-01",
       "end_date": "2026-01-14"
     }
   ]
   ```

## 📱 Mobile Friendly

The dashboard is fully responsive:
- **Desktop**: Side-by-side charts, full navigation
- **Tablet**: Stacked charts with optimized spacing
- **Mobile**: Single column layout, touch-friendly controls

## 🎯 Design Principles

- **Minimal**: Clean, uncluttered interface
- **Fast**: Optimized loading with skeleton states
- **Accessible**: Semantic HTML and ARIA labels
- **Professional**: Polished UI with consistent spacing and typography

## 📁 Project Structure

```
frontend/
├── app/
│   ├── layout.tsx          # Root layout with metadata
│   ├── page.tsx             # Dashboard page
│   └── globals.css          # Global styles
├── components/
│   ├── DateRangePicker.tsx  # Date range selector
│   ├── SpendTrendChart.tsx  # Daily spend line chart
│   ├── CostByModelChart.tsx # Model cost bar chart
│   ├── CostByTeamChart.tsx  # Team cost pie chart
│   └── HealthStatus.tsx     # API health indicator
├── .env.local               # Environment variables
├── package.json             # Dependencies
└── README.md                # This file
```

## 🐛 Troubleshooting

### API Connection Issues

**Problem**: Charts show "API Offline"
**Solution**: 
1. Ensure backend is running: `docker-compose ps`
2. Check backend health: `curl http://localhost:8000/health`
3. Verify `.env.local` has correct `NEXT_PUBLIC_API_BASE_URL`
4. Check browser console for CORS errors

### No Data Showing

**Problem**: Charts display "No data available"
**Solution**:
1. Verify backend has ingested data: `curl http://localhost:8000/api/v1/admin/ingest/cost/mock -H "X-API-Key: heliox-admin-key-change-in-production"`
2. Check date range matches available data
3. Inspect network tab in browser DevTools

### Build Errors

**Problem**: `npm run build` fails
**Solution**:
1. Delete `.next` folder: `rm -rf .next`
2. Clear npm cache: `npm cache clean --force`
3. Reinstall: `rm -rf node_modules && npm install`

## 🚧 Future Enhancements

- [ ] Add daily spend endpoint (currently mocked)
- [ ] Implement authentication/login
- [ ] Add more chart types (scatter, heatmap)
- [ ] Export data to CSV/Excel
- [ ] Dark mode support
- [ ] Real-time updates via WebSocket
- [ ] Cost forecasting
- [ ] Budget alerts

## 📄 License

Part of the Heliox AI project.

## 🤝 Contributing

When adding new features:
1. Follow TypeScript strict mode
2. Use TailwindCSS utility classes
3. Ensure mobile responsiveness
4. Add loading and error states
5. Update this README

## 🎉 Ready!

Your Heliox dashboard should now be running at http://localhost:3000

For backend setup, see `/backend/README.md`
