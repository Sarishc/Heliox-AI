# Heliox-AI Screenshot Guide for LinkedIn

## 🎯 Goal
Capture professional, high-quality screenshots that showcase the Heliox platform for LinkedIn and portfolio use.

## 🖥️ Browser Setup

### Chrome Settings (Recommended)
1. **Open Clean Profile**
   ```bash
   # Launch Chrome in incognito or clean profile
   open -na "Google Chrome" --args --incognito
   ```

2. **Window Size**
   - **Desktop**: 1920x1080 (Full HD)
   - **Tablet**: 1024x768 (iPad)
   - **Mobile**: 375x667 (iPhone)

3. **Zoom Level**
   - Set to 100% (Cmd + 0)
   - Check with View → Actual Size

4. **Hide Unnecessary UI**
   - Hide bookmarks bar (Cmd + Shift + B)
   - Enter full screen if needed (Cmd + Ctrl + F)
   - Hide extensions

## 📸 Screenshot Recommendations

### 1. Dashboard Overview (Primary Screenshot)

**URL**: http://localhost:3000

**Setup**:
- Full window (1920x1080)
- Zoom: 100%
- Date range: January 1 - January 14, 2026 (default)
- Wait for all charts to load

**What to Capture**:
- Header with "Heliox-AI Dashboard" title
- Green health indicator ("API Connected")
- Date range picker
- All three charts:
  - Daily Spend Trend (line chart)
  - Cost by Model (bar chart)
  - Cost by Team (pie chart)

**Screenshot Tool**:
```bash
# macOS built-in (Shift + Cmd + 4, then spacebar)
# Or use Cmd + Shift + 3 for full screen

# Alternative: Use Chrome DevTools
1. Right-click → Inspect
2. Cmd + Shift + P
3. Type "screenshot"
4. Select "Capture full size screenshot"
```

**File Name**: `heliox-dashboard-overview.png`

---

### 2. Cost by Model Chart (Detail Shot)

**URL**: http://localhost:3000

**Setup**:
- Zoom in slightly (110-120%) or crop in post
- Focus on the "Cost by Model" bar chart
- Hover over a bar to show tooltip

**What to Capture**:
- Bar chart with model names on X-axis
- Dollar amounts on Y-axis
- Tooltip showing exact cost value
- Clean, professional colors

**File Name**: `heliox-cost-by-model.png`

---

### 3. Mobile View (Responsive Design)

**URL**: http://localhost:3000

**Setup**:
1. Open Chrome DevTools (Cmd + Option + I)
2. Toggle device toolbar (Cmd + Shift + M)
3. Select "iPhone 12 Pro" or "iPhone 14 Pro"
4. Orientation: Portrait
5. Show device frame (optional)

**What to Capture**:
- Full mobile view with all components stacked
- Responsive layout
- Touch-friendly date picker
- Charts adapting to mobile size

**Screenshot Tool**:
```bash
# In DevTools:
1. Cmd + Shift + P
2. Type "screenshot"
3. Select "Capture full size screenshot"
```

**File Name**: `heliox-mobile-responsive.png`

---

### 4. API Documentation (Technical)

**URL**: http://localhost:8000/docs

**Setup**:
- Full window (1920x1080)
- Expand a few endpoint sections
- Show GET /api/v1/analytics/cost/by-model expanded

**What to Capture**:
- FastAPI Swagger UI
- List of endpoints
- Expanded endpoint with parameters
- Professional API documentation

**File Name**: `heliox-api-docs.png`

---

### 5. Analytics in Action (Interactive)

**URL**: http://localhost:3000

**Setup**:
- Change date range to show different data
- Hover over chart elements to show tooltips
- Show loading states if possible (change dates quickly)

**What to Capture**:
- Active state (tooltip visible)
- Interactive elements highlighted
- Clean data visualization

**File Name**: `heliox-analytics-interactive.png`

---

## 🎨 Post-Processing Tips

### Recommended Tools
- **macOS Preview**: Basic cropping and annotations
- **Figma**: Professional layouts and mockups
- **Canva**: Social media templates
- **Photoshop/GIMP**: Advanced editing

### Enhancements
1. **Add Drop Shadows**
   - Subtle shadow for depth
   - 5-10px blur, 50% opacity

2. **Crop for Focus**
   - Remove extra whitespace
   - Center key elements

3. **Annotations (Optional)**
   - Arrow pointing to key features
   - Text labels for important elements
   - Use platform colors (blue, purple)

4. **Create a Collage**
   - Combine 2-3 screenshots
   - Show desktop + mobile side-by-side
   - Add your name/title overlay

### LinkedIn Image Specs
- **Recommended Size**: 1200x627px (1.91:1 ratio)
- **Max File Size**: 5MB
- **Format**: PNG or JPG
- **Aspect Ratio**: 1.91:1 for best display

## 📱 LinkedIn Post Structure

### Option 1: Single Image Post
- Use Dashboard Overview screenshot
- Clean, professional, full-width view
- Shows all key features

### Option 2: Carousel Post
1. **Slide 1**: Dashboard overview
2. **Slide 2**: Cost by Model chart
3. **Slide 3**: Mobile responsive view
4. **Slide 4**: Architecture diagram (create with Excalidraw)
5. **Slide 5**: "Built with..." tech stack slide

### Option 3: Video + Screenshot
- Record 30-second demo video
- Use screenshot as thumbnail
- Show interaction with charts

## 🎬 Quick Video Demo (Optional)

### Recording Setup
```bash
# Use QuickTime (macOS)
1. Open QuickTime Player
2. File → New Screen Recording
3. Click options → Show mouse clicks
4. Record 30-60 seconds

# Or use Loom
1. Install Loom extension
2. Record screen + webcam (optional)
3. Trim and export
```

### Demo Script (30 seconds)
1. **0-5s**: Show dashboard loading with all charts
2. **5-10s**: Change date range
3. **10-15s**: Hover over Cost by Model chart
4. **15-20s**: Show Cost by Team pie chart
5. **20-25s**: Scroll to show health indicator
6. **25-30s**: Quick view of mobile responsive design

### Video Specs for LinkedIn
- **Max Duration**: 10 minutes (but 30-60s recommended)
- **Max File Size**: 5GB
- **Format**: MP4, MOV
- **Aspect Ratio**: 16:9 or 1:1 (square)

## ✅ Pre-Screenshot Checklist

Before taking screenshots:

### Backend
- [ ] Backend running: `docker-compose ps`
- [ ] Cost data ingested (28 records)
- [ ] Health check returns OK: `curl http://localhost:8000/health`
- [ ] No errors in logs: `docker-compose logs api --tail=20`

### Frontend
- [ ] Frontend running: http://localhost:3000
- [ ] No console errors (F12 → Console)
- [ ] Charts loaded with data
- [ ] Health indicator green
- [ ] Date picker showing default dates

### Browser
- [ ] Incognito/clean profile
- [ ] Bookmarks bar hidden
- [ ] Extensions hidden
- [ ] Zoom at 100%
- [ ] Window at correct size (1920x1080)

## 🖼️ Screenshot Examples

### Good Screenshot ✅
- Clean, professional interface
- All elements loaded
- No browser UI visible (or minimal)
- High resolution (1920x1080+)
- Proper lighting/contrast
- Data visible and legible

### Bad Screenshot ❌
- Loading spinners visible
- Console errors showing
- Browser extensions visible
- Low resolution/blurry
- Awkward crop
- Half-loaded content

## 📊 Data Quality

Ensure your data looks good:
- Cost data: 28 records (Jan 1-14)
- Values: $1,000 - $2,800 per day
- Charts: All showing data (not empty)
- Tooltips: Working on hover

## 🎯 Caption Ideas

### Short Caption (Twitter/X)
```
🚀 Built Heliox - GPU cost analytics for ML teams

Stack: FastAPI + Next.js + PostgreSQL
Features: Real-time analytics, multi-model tracking, mobile-responsive

Live demo 👇
#MachineLearning #FullStack #FastAPI #NextJS
```

### Medium Caption (LinkedIn)
```
🚀 Excited to share Heliox - A full-stack GPU cost analytics platform!

Designed to help ML teams track and optimize infrastructure spending.

Tech Stack:
• FastAPI + PostgreSQL + SQLAlchemy 2.0
• Next.js 14 + TypeScript + TailwindCSS
• Docker Compose

Key Features:
✅ Real-time cost analytics
✅ Multi-model & team tracking
✅ Date range filtering
✅ Mobile-responsive dashboard

The platform aggregates GPU costs across models and teams, providing
actionable insights for optimizing AI infrastructure.

#MachineLearning #FullStack #DevOps
```

### Long Caption (LinkedIn)
```
🚀 Excited to share Heliox - A production-ready GPU cost analytics platform!

Over the past few days, I built a full-stack solution to help ML teams
track and optimize their infrastructure spending across multiple models,
teams, and cloud providers.

🛠 Tech Stack:
• Backend: FastAPI + PostgreSQL + SQLAlchemy 2.0 + Redis
• Frontend: Next.js 14 + TypeScript + TailwindCSS
• Visualization: Recharts
• Infrastructure: Docker Compose

✨ Key Features:
✅ Real-time cost analytics with interactive charts
✅ Multi-team & multi-model cost tracking
✅ Date range filtering for historical analysis
✅ JWT authentication + API key authorization
✅ Idempotent data ingestion (no duplicates)
✅ Mobile-responsive modern UI
✅ Production-ready error handling & logging
✅ RESTful API with Swagger documentation

📊 Architecture Highlights:
• FastAPI async endpoints for high performance
• SQLAlchemy 2.0 with proper indexing & constraints
• Next.js App Router for optimal UX
• PostgreSQL with Alembic migrations
• Docker for consistent deployments

The dashboard provides instant insights into GPU spending patterns,
helping organizations make data-driven decisions about their AI
infrastructure investments.

Key learnings from this project:
1. FastAPI's async capabilities enable high-performance APIs
2. SQLAlchemy 2.0's improved type safety catches bugs early
3. Next.js App Router offers excellent performance out-of-the-box
4. Recharts makes data visualization intuitive
5. Docker Compose simplifies local development

What would you add to this platform? I'm thinking about:
• Kubernetes integration for real-time GPU metrics
• Cost forecasting with ML models
• Slack/email alerts for budget thresholds
• Multi-cloud support (AWS, GCP, Azure)

Open to feedback and collaboration! 🚀

#MachineLearning #FullStack #FastAPI #NextJS #DataVisualization 
#DevOps #CloudComputing #SoftwareEngineering #AI #MLOps #Python 
#TypeScript #PostgreSQL #Docker #WebDevelopment

[Include 2-3 screenshots]
```

## 🚀 Quick Start for Screenshots

```bash
# 1. Ensure services are running
docker-compose ps

# 2. Open frontend in Chrome (incognito)
open -na "Google Chrome" --args --incognito "http://localhost:3000"

# 3. Wait for charts to load (5-10 seconds)

# 4. Take screenshot (macOS)
# Press Cmd + Shift + 4, then Spacebar, then click window
# Or press Cmd + Shift + 3 for full screen

# 5. Screenshots saved to Desktop by default
```

## 🎉 Ready to Capture!

You now have everything you need to create professional screenshots
for your LinkedIn post and portfolio.

Good luck showcasing your Heliox platform! 🚀

---

**Pro Tip**: Take multiple screenshots and choose the best ones.
Sometimes charts render differently, and you want to show your
platform at its best!

