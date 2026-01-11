# Domain Deployment Readiness Checklist

**Date:** 2026-01-11  
**Target Domains:** `heliox.ai`, `app.heliox.ai`, `api.heliox.ai`

---

## ✅ Verification Results

### 1. CORS Configuration ✅

**Status:** READY

**Current State:**
- CORS configured via `CORS_ORIGINS` environment variable
- Production validation rejects localhost origins
- Supports multiple domains (JSON array or comma-separated)

**Required Configuration:**
```env
CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]
```

**Action Required:**
- ✅ No code changes needed
- ⚠️ Set `CORS_ORIGINS` environment variable in production

---

### 2. Frontend Routing ✅

**Status:** READY

**Current State:**
- Next.js App Router handles subdomains correctly
- No `basePath` configuration (works on any domain)
- All routes use relative paths (`/`, `/recommendations`, `/landing`)

**Verification:**
- ✅ No hardcoded domain in routing
- ✅ No `basePath` in `next.config.ts`
- ✅ All `Link` components use relative paths
- ✅ All navigation uses Next.js router (relative)

**Action Required:**
- ✅ No code changes needed

---

### 3. Absolute URLs ✅

**Status:** READY (1 minor issue found)

**Current State:**
- API calls use `NEXT_PUBLIC_API_BASE_URL` environment variable
- All internal links use relative paths
- One external link found (API docs link in ForecastCard)

**Issues Found:**
- ⚠️ `ForecastCard.tsx` has link to `${apiBaseUrl}/docs` (line ~365)
  - This is intentional (links to backend API docs)
  - Uses environment variable (domain-safe)
  - **No action needed** - this is correct behavior

**Verification:**
- ✅ No hardcoded `localhost` URLs in production code
- ✅ All API calls use environment variable
- ✅ All internal routing uses relative paths
- ✅ External links use environment variables where needed

**Action Required:**
- ✅ No code changes needed

---

### 4. Cookies/localStorage ✅

**Status:** READY

**Current State:**
- Beta access gate uses `localStorage`
- localStorage is automatically domain-scoped
- No cookie usage (not needed for current features)

**Domain Safety:**
- ✅ localStorage scoped to current domain automatically
- ✅ Beta access code stored per-domain (expected behavior)
- ✅ No cross-domain access issues
- ✅ No cookie domain configuration needed

**Action Required:**
- ✅ No code changes needed

---

### 5. Environment Variable Documentation ✅

**Status:** COMPLETE

**Documentation Created:**
- ✅ `DOMAIN_DEPLOYMENT_README.md` - Comprehensive domain setup guide
- ✅ `backend/README.md` - Updated with domain examples
- ✅ `frontend/README.md` - Updated with custom domain section

**Action Required:**
- ✅ Documentation complete

---

## Domain Deployment Checklist

### Pre-Deployment

- [ ] Backend deployed to Railway
- [ ] Backend custom domain configured (e.g., `api.heliox.ai`)
- [ ] Frontend deployed to Vercel
- [ ] DNS records configured for all domains
- [ ] SSL certificates active (automatic on Vercel/Railway)

### Backend Configuration (Railway)

- [ ] `ENV=production`
- [ ] `CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]`
- [ ] `SECRET_KEY` set (strong random value)
- [ ] `ADMIN_API_KEY` set (strong random value)
- [ ] `DATABASE_URL` configured
- [ ] Migrations run: `railway run alembic upgrade head`
- [ ] Health check passes: `curl https://api.heliox.ai/health`

### Frontend Configuration (Vercel)

- [ ] `NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai`
- [ ] `NEXT_PUBLIC_BETA_ACCESS_CODE` set (if using)
- [ ] Custom domains added in Vercel dashboard
- [ ] DNS verified (green checkmark)
- [ ] Build succeeds
- [ ] Preview deployment tested

### Post-Deployment Verification

- [ ] Landing page loads: `https://heliox.ai/landing`
- [ ] Dashboard loads: `https://app.heliox.ai` (or configured domain)
- [ ] API health check: `curl https://api.heliox.ai/health`
- [ ] CORS working (no browser console errors)
- [ ] Beta access gate works (if configured)
- [ ] All routes functional
- [ ] No console errors

---

## Code Changes Summary

### Files Modified

1. **`DOMAIN_DEPLOYMENT_README.md`** (NEW)
   - Comprehensive domain setup guide
   - Environment variable documentation
   - Troubleshooting section

2. **`backend/README.md`**
   - Updated CORS_ORIGINS example with multiple domains

3. **`frontend/README.md`**
   - Added custom domain setup section
   - Updated deployment examples

### Files Verified (No Changes Needed)

- ✅ `backend/app/core/config.py` - CORS configuration correct
- ✅ `backend/app/main.py` - CORS middleware correct
- ✅ `frontend/next.config.ts` - No basePath needed
- ✅ `frontend/app/page.tsx` - All links relative
- ✅ `frontend/app/recommendations/page.tsx` - All links relative
- ✅ `frontend/lib/beta-access.ts` - localStorage domain-safe
- ✅ `frontend/components/*` - All API calls use environment variables

---

## Domain Configuration Examples

### Recommended Setup

**Domains:**
- `heliox.ai` → Frontend (Landing + Dashboard) - Vercel
- `api.heliox.ai` → Backend API - Railway

**Backend:**
```env
CORS_ORIGINS=["https://heliox.ai"]
```

**Frontend:**
```env
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai
```

### Alternative: Subdomain Setup

**Domains:**
- `heliox.ai` → Landing - Vercel
- `app.heliox.ai` → Dashboard - Vercel
- `api.heliox.ai` → Backend - Railway

**Backend:**
```env
CORS_ORIGINS=["https://heliox.ai","https://app.heliox.ai"]
```

**Frontend:**
```env
NEXT_PUBLIC_API_BASE_URL=https://api.heliox.ai
```

---

## Summary

**Domain Readiness Status:** ✅ **READY**

All domain safety checks passed:
- ✅ CORS supports multiple domains
- ✅ Frontend routing works on any domain/subdomain
- ✅ No absolute URLs hardcoded
- ✅ localStorage/cookies domain-safe
- ✅ Environment variables documented

**No Code Changes Required** - Configuration only.

**Next Steps:**
1. Configure DNS records
2. Set environment variables in Railway/Vercel
3. Deploy and verify

---

**Domain Deployment Ready** ✅
