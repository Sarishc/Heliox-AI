# Starting Heliox Project

## Quick Start

### Prerequisites
1. **Docker Desktop must be running** (required for backend)
2. Node.js 18+ installed (for frontend)

### Start Everything

```bash
# Option 1: Use the demo script (recommended - starts everything)
make demo

# Option 2: Manual start
# 1. Start Docker services (backend)
make start

# 2. In a separate terminal, start frontend
cd frontend
npm run dev
```

### URLs

Once running:
- **Frontend Dashboard**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs (Swagger)**: http://localhost:8000/docs
- **API Docs (ReDoc)**: http://localhost:8000/redoc

---

## Current Status

**Issue:** Docker daemon is not running.

**To fix:**
1. Start Docker Desktop application
2. Wait for Docker to fully start
3. Then run: `make start` or `make demo`

**Frontend:** 
- Running on http://localhost:3000 (if started)
- Uses Next.js dev server

**Backend:**
- Requires Docker (PostgreSQL + Redis)
- API runs on http://localhost:8000

---

## Manual Steps

### Step 1: Start Docker Desktop
- Open Docker Desktop application
- Wait until Docker icon shows "Docker is running"

### Step 2: Start Backend
```bash
cd /Users/sarish/Downloads/Projects/Heliox-AI
make start
# or
docker-compose up -d
```

### Step 3: Start Frontend (if not already running)
```bash
cd frontend
npm run dev
```

### Step 4: Open in Browser
- Frontend: http://localhost:3000
- Backend API Docs: http://localhost:8000/docs

---

## Troubleshooting

**Docker not starting?**
- Check Docker Desktop is installed
- Restart Docker Desktop
- Check system resources (Docker needs memory)

**Port conflicts?**
- Port 8000 (backend): Check with `lsof -ti:8000`
- Port 3000 (frontend): Check with `lsof -ti:3000`
- Port 5432 (PostgreSQL): Check with `lsof -ti:5432`

**Frontend not connecting to backend?**
- Check backend is running: `curl http://localhost:8000/health`
- Check CORS settings in backend
- Verify `NEXT_PUBLIC_API_BASE_URL` in frontend (defaults to http://localhost:8000)
