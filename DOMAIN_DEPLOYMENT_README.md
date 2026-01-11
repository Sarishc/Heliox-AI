# Custom Domain Deployment Guide

**Date:** 2026-01-11  
**Status:** ✅ Domain-Ready

---

## Overview

This guide covers deploying Heliox to custom domains:
- **Landing Page**: `https://heliox.ai`
- **Dashboard**: `https://app.heliox.ai`
- **API**: `https://api.heliox.ai` (or subdomain of choice)

---

## Architecture

### Recommended Domain Setup

- **`heliox.ai`** → Frontend (Landing Page) - Vercel
- **`app.heliox.ai`** → Frontend (Dashboard) - Vercel (same project, different domain)
- **`api.heliox.ai`** → Backend API - Railway

**Alternative:** Use single domain with path-based routing:
- `heliox.ai` → Landing
- `heliox.ai/app` → Dashboard (Next.js handles this automatically)

---

## Backend Configuration

### Required Environment Variables

```env
# Application
ENV=production
LOG_LEVEL=INFO
PORT=8000

# Database
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/db

# CORS - CRITICAL for custom domain
CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]

# Security (REQUIRED)
SECRET_KEY=your-strong-secret-key-here
ADMIN_API_KEY=your-strong-admin-key-here

# Redis (optional)
REDIS_URL=redis://host:6379/0

# Slack (optional)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Scheduling
DAILY_SUMMARY_HOUR=9
TIMEZONE=UTC
```

### CORS Configuration

**Format:** JSON array or comma-separated list

**Railway Environment Variable:**
```
CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]
```

**Or comma-separated (Railway may require this format):**
```
CORS_ORIGINS=https://heliox.ai,https://app.heliox.ai
```

**Important:**
- Include ALL domains that will access the API
- Must include protocol (`https://`)
- No trailing slashes
- Production validation rejects `localhost` origins

---

## Frontend Configuration

### Required Environment Variables

```env
# API Base URL (REQUIRED)
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai

# Beta Access Code (OPTIONAL)
NEXT_PUBLIC_BETA_ACCESS_CODE=your-access-code
```

### Vercel Setup

1. **Add Custom Domains:**
   - Go to Project → Settings → Domains
   - Add `heliox.ai` (primary)
   - Add `app.heliox.ai` (or configure as alias)

2. **Set Environment Variables:**
   - `NEXT_PUBLIC_API_BASE_URL` = `https://api.heliox.ai`
   - `NEXT_PUBLIC_BETA_ACCESS_CODE` (if using beta gate)

3. **DNS Configuration:**
   - Add CNAME records pointing to Vercel
   - `heliox.ai` → `cname.vercel-dns.com`
   - `app.heliox.ai` → `cname.vercel-dns.com` (or same as above)

---

## Domain Safety Verification

### ✅ CORS Configuration
- **Status:** Configurable via `CORS_ORIGINS`
- **Validation:** Production rejects localhost origins
- **Format:** JSON array or comma-separated

### ✅ Frontend Routing
- **Status:** Next.js App Router handles subdomains correctly
- **No basePath needed:** Works on any domain/subdomain
- **All routes relative:** No absolute URLs in routing

### ✅ API Calls
- **Status:** Uses `NEXT_PUBLIC_API_BASE_URL` environment variable
- **No hardcoded URLs:** All API calls use environment config
- **Relative paths:** API endpoints use relative paths (`/api/v1/...`)

### ✅ localStorage Usage
- **Status:** Domain-safe (defaults to current domain)
- **Beta Access Gate:** Uses localStorage, works on any domain
- **No domain restrictions:** localStorage is automatically domain-scoped

### ✅ No Absolute URLs
- **Status:** Verified - no hardcoded absolute URLs in code
- **Links:** All use relative paths (`/recommendations`, `/`, etc.)
- **API:** All use environment variable + relative paths

---

## Deployment Checklist

### Pre-Deployment

- [ ] Backend deployed to Railway with custom domain (e.g., `api.heliox.ai`)
- [ ] Frontend deployed to Vercel
- [ ] DNS records configured (A/CNAME)
- [ ] SSL certificates active (automatic on Vercel/Railway)

### Backend (Railway)

- [ ] `ENV=production` set
- [ ] `CORS_ORIGINS` includes all frontend domains
- [ ] `SECRET_KEY` and `ADMIN_API_KEY` set (strong values)
- [ ] `DATABASE_URL` configured
- [ ] Migrations run: `railway run alembic upgrade head`
- [ ] Health check passes: `curl https://api.heliox.ai/health`

### Frontend (Vercel)

- [ ] `NEXT_PUBLIC_API_BASE_URL` = `https://api.heliox.ai`
- [ ] `NEXT_PUBLIC_BETA_ACCESS_CODE` set (if using)
- [ ] Custom domains added in Vercel dashboard
- [ ] DNS verified (green checkmark in Vercel)
- [ ] Build succeeds: `npm run build`
- [ ] Preview deployment works

### Post-Deployment Verification

- [ ] Landing page loads: `https://heliox.ai/landing`
- [ ] Dashboard loads: `https://app.heliox.ai` (or `https://heliox.ai`)
- [ ] API health check: `curl https://api.heliox.ai/health`
- [ ] CORS working: Dashboard can fetch from API (no CORS errors)
- [ ] Beta access gate works (if configured)
- [ ] All routes work (dashboard, recommendations, landing)
- [ ] No console errors in browser DevTools

---

## Troubleshooting

### CORS Errors

**Symptom:** Browser console shows CORS errors

**Solution:**
1. Verify `CORS_ORIGINS` includes exact domain (with protocol)
2. Check for trailing slashes (remove them)
3. Ensure domains match exactly (case-sensitive for protocol)
4. Restart backend after changing CORS_ORIGINS

**Example:**
```env
# ✅ Correct
CORS_ORIGINS=["https://app.heliox.ai","https://heliox.ai"]

# ❌ Wrong
CORS_ORIGINS=["https://app.heliox.ai/"]  # Trailing slash
CORS_ORIGINS=["http://app.heliox.ai"]    # Wrong protocol
```

### API Connection Issues

**Symptom:** Dashboard shows "API Offline"

**Solution:**
1. Verify `NEXT_PUBLIC_API_BASE_URL` is set correctly
2. Check API is accessible: `curl https://api.heliox.ai/health`
3. Verify CORS configuration
4. Check browser network tab for actual request URLs

### Routing Issues

**Symptom:** 404 errors on routes

**Solution:**
1. Next.js App Router handles all routes automatically
2. No basePath configuration needed
3. Ensure Vercel is serving from root path
4. Check Vercel deployment logs

### localStorage Issues

**Symptom:** Beta access code not persisting

**Solution:**
1. localStorage is domain-scoped automatically
2. Codes from `heliox.ai` won't work on `app.heliox.ai` (different domains)
3. Use same domain for landing and dashboard if sharing access
4. Or use cookie-based storage (requires backend changes)

---

## Domain Configuration Examples

### Single Domain (Recommended for MVP)

**Domains:**
- `heliox.ai` → Frontend (Vercel)
- `api.heliox.ai` → Backend (Railway)

**Backend CORS:**
```
CORS_ORIGINS=["https://heliox.ai"]
```

**Frontend API URL:**
```
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai
```

### Subdomain Setup

**Domains:**
- `heliox.ai` → Landing (Vercel)
- `app.heliox.ai` → Dashboard (Vercel)
- `api.heliox.ai` → Backend (Railway)

**Backend CORS:**
```
CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]
```

**Frontend API URL:**
```
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai
```

---

## Environment Variables Summary

### Backend (Railway)

| Variable | Required | Example | Notes |
|----------|----------|---------|-------|
| `ENV` | Yes | `production` | Environment name |
| `CORS_ORIGINS` | Yes | `["https://heliox.ai","https://app.heliox.ai"]` | JSON array or comma-separated |
| `SECRET_KEY` | Yes | `strong-random-key-32-chars+` | JWT secret |
| `ADMIN_API_KEY` | Yes | `strong-random-key` | Admin endpoint key |
| `DATABASE_URL` | Yes | `postgresql://...` | PostgreSQL connection |
| `REDIS_URL` | No | `redis://...` | Optional caching |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `PORT` | No | `8000` | Server port (Railway provides) |

### Frontend (Vercel)

| Variable | Required | Example | Notes |
|----------|----------|---------|-------|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | `https://api.heliox.ai` | Backend API root URL |
| `NEXT_PUBLIC_BETA_ACCESS_CODE` | No | `heliox-beta-2024` | Optional beta gate |

---

## Security Notes

1. **CORS:** Production validation ensures no localhost origins
2. **localStorage:** Domain-scoped automatically (secure by default)
3. **API Keys:** Must be strong random values (not defaults)
4. **HTTPS:** Required for production (automatic on Vercel/Railway)
5. **Secrets:** Never commit secrets to repository

---

## Quick Reference

### Backend Health Check
```bash
curl https://api.heliox.ai/health
```

### Test CORS
```bash
curl -H "Origin: https://app.heliox.ai" \
     -H "Access-Control-Request-Method: GET" \
     -H "Access-Control-Request-Headers: X-Requested-With" \
     -X OPTIONS \
     https://api.heliox.ai/health
```

### Verify Frontend API Config
```bash
# Check environment variable is set
vercel env ls

# Check in browser console
console.log(process.env.NEXT_PUBLIC_API_BASE_URL)
```

---

**Domain Deployment Ready** ✅  
All domain safety checks passed.
