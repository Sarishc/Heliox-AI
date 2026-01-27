# Heliox Production Deployment Guide

This guide walks you through deploying Heliox to production for real startup use.

---

## Prerequisites

- [ ] Domain name (e.g., `yourstartup.com`)
- [ ] Cloud account (Railway, AWS, GCP, or Azure)
- [ ] GitHub account (for code repository)
- [ ] Basic terminal/command line knowledge

---

## Deployment Options (Ranked by Ease)

### 🥇 **Option 1: Railway (Recommended for Startups)**
- **Difficulty**: Easy ⭐
- **Time**: 30 minutes
- **Cost**: $20-50/month
- **Best for**: MVP, small teams, quick iteration

### 🥈 **Option 2: Vercel + Render**
- **Difficulty**: Medium ⭐⭐
- **Time**: 1 hour
- **Cost**: $25-75/month
- **Best for**: Frontend-heavy apps, Next.js optimization

### 🥉 **Option 3: AWS (ECS + RDS)**
- **Difficulty**: Hard ⭐⭐⭐⭐
- **Time**: 4-6 hours
- **Cost**: $100-300/month
- **Best for**: Enterprise customers, strict compliance needs

---

## Option 1: Deploy to Railway (Fastest)

### Step 1: Prepare Your Repository

1. **Push code to GitHub**:
   ```bash
   cd /Users/sarish/Downloads/Projects/Heliox-AI
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/heliox.git
   git push -u origin main
   ```

2. **Generate secure credentials**:
   ```bash
   # Generate random secure keys
   export SECRET_KEY=$(openssl rand -base64 32)
   export ADMIN_API_KEY=$(openssl rand -base64 32)
   
   # Save these! You'll need them.
   echo "SECRET_KEY=$SECRET_KEY" > .credentials.txt
   echo "ADMIN_API_KEY=$ADMIN_API_KEY" >> .credentials.txt
   ```

### Step 2: Deploy Backend to Railway

1. **Sign up** at [railway.app](https://railway.app)

2. **Create new project** → "Deploy from GitHub"

3. **Add PostgreSQL**:
   - Click "New" → "Database" → "PostgreSQL"
   - Railway will generate `DATABASE_URL` automatically

4. **Add Redis**:
   - Click "New" → "Database" → "Redis"
   - Railway will generate `REDIS_URL` automatically

5. **Deploy Backend API**:
   - Click "New" → "GitHub Repo" → Select your repo → Choose `backend/`
   - Railway will detect Dockerfile and deploy

6. **Configure Environment Variables**:
   Go to API service → "Variables" tab:
   ```
   ENV=production
   LOG_LEVEL=INFO
   SECRET_KEY=<paste_from_.credentials.txt>
   ADMIN_API_KEY=<paste_from_.credentials.txt>
   DATABASE_URL=${{Postgres.DATABASE_URL}}
   REDIS_URL=${{Redis.REDIS_URL}}
   CORS_ORIGINS=["https://your-app.up.railway.app","https://yourdomain.com"]
   MULTI_TENANT=true
   PORT=8000
   ```

7. **Deploy Worker & Beat**:
   - Add another service from same repo
   - Set same environment variables
   - Override start command:
     - Worker: `celery -A app.celery_app worker --loglevel=info`
     - Beat: `celery -A app.celery_app beat --loglevel=info`

8. **Run Migrations**:
   ```bash
   railway run --service=api alembic upgrade head
   ```

9. **Create First Team**:
   ```bash
   ADMIN_KEY=<your_admin_api_key>
   API_URL=<your_railway_api_url>
   
   curl -X POST $API_URL/api/v1/admin/onboard \
     -H "X-API-Key: $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "team_name": "Your Startup",
       "api_key_name": "Production Key",
       "monthly_budget_usd": 50000
     }'
   
   # Save the returned api_key!
   ```

### Step 3: Deploy Frontend to Vercel

1. **Sign up** at [vercel.com](https://vercel.com)

2. **Import project** from GitHub

3. **Configure Build**:
   - Framework: Next.js
   - Root directory: `apps/app`
   - Build command: `pnpm build`
   - Output directory: `.next`

4. **Set Environment Variables**:
   ```
   NEXT_PUBLIC_API_BASE_URL=https://your-api.up.railway.app
   ```
   **DO NOT SET** `NEXT_PUBLIC_DEV_ADMIN_API_KEY` in production!

5. **Deploy**: Vercel auto-deploys

6. **Add Custom Domain** (optional):
   - Go to "Settings" → "Domains"
   - Add your domain
   - Update DNS records as instructed

### Step 4: Verify Deployment

1. **Test API Health**:
   ```bash
   curl https://your-api.up.railway.app/health
   # Expected: {"status":"ok"}
   ```

2. **Test Dashboard**:
   - Visit: `https://your-app.vercel.app`
   - Should see login/signup page
   - Register a user, create team, get API key

3. **Ingest Test Data**:
   ```bash
   API_KEY=<your_production_api_key>
   
   # Send cost data
   curl -X POST https://your-api.up.railway.app/api/v1/ingest/cost \
     -H "X-API-Key: $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "records": [
         {"date":"2026-01-01","provider":"aws","gpu_type":"a100","cost_usd":1000}
       ]
     }'
   ```

4. **Check Dashboard**:
   - Go to dashboard
   - Should see cost data appearing

---

## Option 2: Deploy to Vercel + Render

### Backend on Render:

1. **Sign up** at [render.com](https://render.com)

2. **Create PostgreSQL Database**:
   - New → PostgreSQL
   - Name: `heliox-db`
   - Save the internal connection string

3. **Create Redis Instance**:
   - New → Redis
   - Save the internal connection string

4. **Create Web Service**:
   - New → Web Service
   - Connect GitHub repo
   - Root directory: `backend`
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

5. **Add Environment Variables**:
   ```
   ENV=production
   SECRET_KEY=<generate_with_openssl>
   ADMIN_API_KEY=<generate_with_openssl>
   DATABASE_URL=${{heliox-db.DATABASE_URL}}
   REDIS_URL=${{redis.REDIS_URL}}
   CORS_ORIGINS=["https://your-app.vercel.app"]
   ```

6. **Create Background Worker**:
   - New → Background Worker (from same repo)
   - Start command: `celery -A app.celery_app worker --loglevel=info`
   - Same environment variables

7. **Create Celery Beat**:
   - New → Background Worker
   - Start command: `celery -A app.celery_app beat --loglevel=info`
   - Same environment variables

### Frontend on Vercel:
(Same as Option 1, Step 3)

---

## Option 3: Deploy to AWS (Enterprise)

### Architecture:
- **API**: ECS Fargate (auto-scaling)
- **Database**: RDS PostgreSQL (Multi-AZ)
- **Cache**: ElastiCache Redis
- **Load Balancer**: ALB with SSL
- **Frontend**: Vercel or Amplify
- **Logs**: CloudWatch
- **Metrics**: CloudWatch + Prometheus

### Step-by-Step:

1. **Create VPC** with public and private subnets

2. **Deploy RDS PostgreSQL**:
   ```bash
   aws rds create-db-instance \
     --db-instance-identifier heliox-db \
     --db-instance-class db.t3.medium \
     --engine postgres \
     --engine-version 15.4 \
     --allocated-storage 100 \
     --master-username heliox \
     --master-user-password <secure_password> \
     --vpc-security-group-ids sg-xxxxx \
     --db-subnet-group-name heliox-subnet-group \
     --multi-az \
     --backup-retention-period 7
   ```

3. **Deploy ElastiCache Redis**:
   ```bash
   aws elasticache create-replication-group \
     --replication-group-id heliox-redis \
     --replication-group-description "Heliox Redis" \
     --engine redis \
     --cache-node-type cache.t3.micro \
     --num-cache-clusters 2 \
     --automatic-failover-enabled
   ```

4. **Build and Push Docker Image**:
   ```bash
   # Create ECR repository
   aws ecr create-repository --repository-name heliox-api
   
   # Build and push
   docker build -t heliox-api ./backend
   docker tag heliox-api:latest <account>.dkr.ecr.us-east-1.amazonaws.com/heliox-api:latest
   docker push <account>.dkr.ecr.us-east-1.amazonaws.com/heliox-api:latest
   ```

5. **Create ECS Task Definition**:
   ```json
   {
     "family": "heliox-api",
     "networkMode": "awsvpc",
     "requiresCompatibilities": ["FARGATE"],
     "cpu": "512",
     "memory": "1024",
     "containerDefinitions": [{
       "name": "api",
       "image": "<account>.dkr.ecr.us-east-1.amazonaws.com/heliox-api:latest",
       "portMappings": [{"containerPort": 8000}],
       "environment": [
         {"name": "ENV", "value": "production"},
         {"name": "DATABASE_URL", "value": "<from_rds>"},
         {"name": "REDIS_URL", "value": "<from_elasticache>"}
       ],
       "secrets": [
         {"name": "SECRET_KEY", "valueFrom": "arn:aws:secretsmanager:..."},
         {"name": "ADMIN_API_KEY", "valueFrom": "arn:aws:secretsmanager:..."}
       ],
       "logConfiguration": {
         "logDriver": "awslogs",
         "options": {
           "awslogs-group": "/ecs/heliox-api",
           "awslogs-region": "us-east-1",
           "awslogs-stream-prefix": "api"
         }
       }
     }]
   }
   ```

6. **Create ECS Service** with Application Load Balancer

7. **Configure SSL** with ACM certificate

8. **Set up Auto Scaling** based on CPU/memory

(Full AWS guide would be 20+ pages - recommend using Railway instead for MVP)

---

## Post-Deployment Checklist

### Immediately After Deploy:

- [ ] **Test all health endpoints**:
  ```bash
  curl https://api.yourdomain.com/health
  curl https://api.yourdomain.com/ready
  curl https://api.yourdomain.com/health/db
  ```

- [ ] **Create admin user and team**:
  ```bash
  # Register first user
  curl -X POST https://api.yourdomain.com/api/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"email":"admin@yourstartup.com","password":"<secure>","full_name":"Admin"}'
  
  # Login
  curl -X POST https://api.yourdomain.com/api/v1/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=admin@yourstartup.com&password=<secure>"
  
  # Onboard team (use admin API key)
  curl -X POST https://api.yourdomain.com/api/v1/admin/onboard \
    -H "X-API-Key: $ADMIN_API_KEY" \
    -d '{"team_name":"Your Startup","api_key_name":"Production","monthly_budget_usd":100000}'
  ```

- [ ] **Test data ingestion**:
  ```bash
  # Use the API key from onboarding
  curl -X POST https://api.yourdomain.com/api/v1/ingest/cost \
    -H "X-API-Key: <team_api_key>" \
    -d '{"records":[{"date":"2026-01-01","provider":"aws","gpu_type":"a100","cost_usd":500}]}'
  ```

- [ ] **Verify dashboard loads**:
  - Visit `https://your-app.vercel.app`
  - Login with admin credentials
  - Check all widgets load without errors

- [ ] **Configure alerts**:
  ```bash
  # Set Slack webhook for your team
  curl -X POST https://api.yourdomain.com/api/v1/alerts/webhook \
    -H "Authorization: Bearer <access_token>" \
    -d '{"team_id":"<id>","slack_webhook_url":"https://hooks.slack.com/services/..."}'
  ```

### Within 24 Hours:

- [ ] **Set up monitoring**:
  - Add Sentry: `pip install sentry-sdk[fastapi]`
  - Configure in `app/main.py`:
    ```python
    import sentry_sdk
    sentry_sdk.init(dsn="https://...@sentry.io/...")
    ```

- [ ] **Configure backups**:
  - Railway: Automatic (included)
  - AWS RDS: Enable automated backups (7-day retention)
  - Download initial backup to local storage

- [ ] **Test disaster recovery**:
  - Create test team with data
  - Restore from backup
  - Verify data integrity

- [ ] **Set up uptime monitoring**:
  - Use: UptimeRobot, Pingdom, or Better Uptime
  - Monitor: `/health` endpoint every 5 minutes
  - Alert: Via email/Slack on downtime

### Within 1 Week:

- [ ] **Add custom domain**:
  - Frontend: Configure in Vercel
  - Backend: Configure in Railway/AWS
  - Update CORS_ORIGINS

- [ ] **Enable SSL/HTTPS**:
  - Vercel: Automatic ✅
  - Railway: Automatic ✅
  - AWS: Use ACM + ALB

- [ ] **Create onboarding documentation** for your customers

- [ ] **Load test** with realistic data volume:
  ```bash
  # Install k6 or Apache Bench
  k6 run loadtest.js  # 100 concurrent users for 5 minutes
  ```

- [ ] **Review logs for errors**:
  - Check for 500 errors
  - Check for slow queries (> 1 second)
  - Fix any issues found

---

## Environment Variables Reference

### Backend (Required):

```bash
# Core Application
ENV=production                    # Options: dev, staging, production
LOG_LEVEL=INFO                    # Options: DEBUG, INFO, WARNING, ERROR
PORT=8000                         # Railway sets this automatically

# Security (MUST CHANGE FROM DEFAULTS)
SECRET_KEY=<openssl rand -base64 32>
ADMIN_API_KEY=<openssl rand -base64 32>

# Database (Set by managed service)
DATABASE_URL=postgresql+psycopg2://user:pass@host:5432/dbname

# Redis (Set by managed service)
REDIS_URL=redis://host:6379/0

# CORS (Set to your frontend domain)
CORS_ENABLED=true
CORS_ORIGINS=["https://app.yourdomain.com"]

# Multi-Tenancy
MULTI_TENANT=true                 # Always true for SaaS

# Optional: Slack Alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
DAILY_SUMMARY_HOUR=9              # 9 AM summary
TIMEZONE=America/New_York         # Your timezone
```

### Frontend (Required):

```bash
# apps/app/.env.local
NEXT_PUBLIC_API_BASE_URL=https://api.yourdomain.com

# DO NOT SET in production:
# NEXT_PUBLIC_DEV_ADMIN_API_KEY  (dev only)
```

---

## Troubleshooting Common Deployment Issues

### Issue: "Database connection failed"
**Solution**:
- Check `DATABASE_URL` format: `postgresql+psycopg2://user:password@host:port/dbname`
- Verify database is accessible from API container
- Check firewall rules (Railway handles this automatically)

### Issue: "Migrations not applied"
**Solution**:
```bash
# SSH into API container or use Railway CLI
railway run alembic upgrade head

# Verify current version
railway run alembic current
# Expected: 015 (head)
```

### Issue: "Frontend shows 401 Unauthorized"
**Solution**:
- Check `NEXT_PUBLIC_API_BASE_URL` is set correctly
- Verify CORS_ORIGINS includes your frontend domain
- Clear browser localStorage and try again
- Check network tab for exact error response

### Issue: "Celery Beat not running scheduled tasks"
**Solution**:
- Check Beat container logs: `docker logs heliox-beat`
- Verify `/app/data` directory has write permissions
- Restart Beat container: `docker-compose restart beat`

### Issue: "Rate limiting not working"
**Solution**:
- Rate limiting middleware is enabled but limits may be too high for production
- Update `app/core/rate_limit.py` with stricter limits

### Issue: "Slow API responses"
**Solution**:
- Enable query logging: Set `LOG_LEVEL=DEBUG` temporarily
- Check database indexes: `EXPLAIN ANALYZE SELECT ...`
- Add Redis caching to expensive endpoints
- Increase container resources (CPU/memory)

---

## Security Checklist for Production

- [ ] **Changed all default credentials** (SECRET_KEY, ADMIN_API_KEY, DB password)
- [ ] **Enabled HTTPS** (SSL certificate)
- [ ] **Configured CORS** (specific domains, not wildcard)
- [ ] **Disabled debug mode** (`ENV=production`)
- [ ] **Removed demo/test endpoints** (auto-disabled in production)
- [ ] **Enabled request logging** (for audit trail)
- [ ] **Set up firewall rules** (allow only necessary ports)
- [ ] **Configured secrets manager** (AWS Secrets Manager, etc.)
- [ ] **Enabled database encryption** (at rest and in transit)
- [ ] **Set up rate limiting** (prevent DoS)
- [ ] **Added uptime monitoring** (detect outages)
- [ ] **Tested disaster recovery** (restore from backup)

---

## Cost Estimates

### Railway (Hobby/Starter):
- PostgreSQL: $5/month (500MB)
- Redis: $5/month (100MB)
- API Service: $5/month (512MB RAM)
- Worker: $5/month
- Beat: $5/month
**Total**: ~$25/month + usage

### Railway (Scale):
- PostgreSQL: $25/month (8GB)
- Redis: $10/month (1GB)
- API Service: $20/month (2GB RAM, autoscaling)
- Worker: $10/month
- Beat: $5/month
**Total**: ~$70/month + usage

### AWS (Production):
- RDS db.t3.medium: $60/month
- ElastiCache t3.micro: $15/month
- ECS Fargate (2 tasks): $40/month
- ALB: $20/month
- Data transfer: $10/month
**Total**: ~$145/month

### Vercel (Frontend):
- Free tier: $0/month (hobby)
- Pro tier: $20/month (custom domain, analytics)

---

## Maintenance Schedule

### Daily:
- [ ] Check error logs for new issues
- [ ] Monitor API response times
- [ ] Review Celery task failures

### Weekly:
- [ ] Review security alerts
- [ ] Check database size growth
- [ ] Verify backups are running

### Monthly:
- [ ] Review and optimize slow queries
- [ ] Update dependencies (`pip list --outdated`)
- [ ] Review and renew SSL certificates (auto-renewed usually)
- [ ] Check for new feature requests

---

## Support & Resources

- **API Documentation**: `https://api.yourdomain.com/docs`
- **Health Check**: `https://api.yourdomain.com/health`
- **Logs**: Railway dashboard or AWS CloudWatch
- **Database Admin**: Use TablePlus, pgAdmin, or Postico

---

## Next Steps After Deployment

1. **Invite your first customer**
2. **Monitor for errors** closely for first week
3. **Gather feedback** on missing features
4. **Implement critical fixes** from audit report
5. **Add comprehensive tests** (target: 70% coverage)
6. **Write user documentation** (how to use dashboard)
7. **Create video tutorial** (5-minute quickstart)

---

*This guide will get you from zero to production in < 2 hours using Railway, or < 1 day using AWS.*
