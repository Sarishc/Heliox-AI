# Heliox-AI Backend

FastAPI backend for GPU cost optimization and capacity planning.

## Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (copy from .env.example)
cp .env.example .env

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

## Deployment

### Railway Deployment

Railway automatically detects this Python application. The backend is configured to:

- Bind to `0.0.0.0:$PORT` (Railway provides PORT env var)
- Use `DATABASE_URL` for PostgreSQL connection
- Use `REDIS_URL` for Redis connection (optional)
- Validate database connectivity on startup (production/staging)

#### Required Environment Variables

**Critical (application will not start without these):**

- `SECRET_KEY` - Cryptographically secure random string (32+ bytes)
- `ADMIN_API_KEY` - Strong random API key for admin endpoints
- `DATABASE_URL` - PostgreSQL connection string (Railway provides this if you add PostgreSQL service)
- `ENV` - Set to `production` for production deployments
- `CORS_ORIGINS` - JSON array of allowed origins, e.g., `["https://yourdomain.com"]`

**Recommended:**

- `REDIS_URL` - Redis connection string (if using caching/forecasting)
- `LOG_LEVEL` - `INFO` or `WARNING` (not DEBUG in production)
- `SLACK_WEBHOOK_URL` - For Slack notifications (optional)

#### Railway Setup Steps

1. **Connect Repository** to Railway
2. **Add PostgreSQL Service** - Railway will automatically set `DATABASE_URL`
3. **Add Redis Service** (optional) - Railway will automatically set `REDIS_URL`
4. **Set Environment Variables:**
   - `ENV=production`
   - `SECRET_KEY` - Generate with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `ADMIN_API_KEY` - Generate a strong random key
   - `CORS_ORIGINS` - Set to your frontend domain(s): 
     - Single domain: `["https://heliox.ai"]`
     - Multiple domains: `["https://heliox.ai","https://app.heliox.ai"]`
     - Format: JSON array or comma-separated list
   - `LOG_LEVEL=INFO`
5. **Run Migrations:**
   
   **IMPORTANT:** Migrations are NOT run automatically on startup. Run them manually:
   
   **Option 1: Railway CLI (Recommended)**
   ```bash
   railway run alembic upgrade head
   ```
   
   **Option 2: Railway Dashboard**
   - Go to your service → "Deployments" → "Run Command"
   - Run: `alembic upgrade head`
   
   **Option 3: Migration Script**
   ```bash
   railway run python scripts/migrate.py
   ```
   
   **Check Migration Status:**
   ```bash
   railway run python scripts/migrate.py --current
   railway run python scripts/migrate.py --history
   ```
   
6. **Deploy** - Railway will auto-deploy on git push

#### Startup Logs

On startup, the application logs:
- Environment name
- Database connection status
- Port binding
- Configuration validation status

Example startup log:
```
============================================================
Starting Heliox-AI
Environment: production
Log level: INFO
Port: 8000
✓ Database connection validated successfully
Startup complete - Database: connected
============================================================
```

### Health Checks

- `GET /health` - Basic health check
- `GET /health/db` - Database connection health check

Railway will use `/health` for health monitoring.

### API Documentation

- Swagger UI: `https://your-app.railway.app/docs`
- ReDoc: `https://your-app.railway.app/redoc`

## Development

### Project Structure

```
backend/
├── app/
│   ├── api/          # API routes
│   ├── core/         # Core configuration, DB, logging
│   ├── models/       # SQLAlchemy models
│   ├── schemas/      # Pydantic schemas
│   ├── services/     # Business logic
│   └── main.py       # FastAPI app entry point
├── alembic/          # Database migrations
├── requirements.txt  # Python dependencies
└── Procfile          # Railway deployment command
```

### Running Tests

```bash
pytest
pytest --cov=app --cov-report=html
```

### Database Migrations

**Production Safety:** Migrations are NEVER run automatically on application startup. They must be run manually.

#### Local Development

```bash
# Create migration (after model changes)
alembic revision --autogenerate -m "description of changes"

# Apply migrations
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history --verbose

# Rollback one migration (use with caution)
alembic downgrade -1
```

#### Production Deployment (Railway)

**Before deploying code with new migrations:**

1. **Review the migration file** in `alembic/versions/` to ensure it's safe
2. **Run migrations manually:**
   ```bash
   railway run alembic upgrade head
   ```
3. **Verify migration status:**
   ```bash
   railway run alembic current
   ```

**Alternative: Use Migration Script**

The `scripts/migrate.py` script provides additional safety checks:

```bash
# Check current status
railway run python scripts/migrate.py --current

# View history
railway run python scripts/migrate.py --history

# Run migrations
railway run python scripts/migrate.py

# Dry run (shows what would be executed)
railway run python scripts/migrate.py --dry-run
```

**Migration Best Practices:**
- Always review migration files before running in production
- Test migrations on staging first
- Backup database before running migrations
- Run migrations during low-traffic windows
- Monitor application logs after migration

## Configuration

All configuration is managed via environment variables. See `.env.example` for available options.

The application validates production settings on startup and will fail fast with clear error messages if required configuration is missing.
