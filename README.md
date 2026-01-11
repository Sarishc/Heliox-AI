# Heliox-AI Backend

Production-grade FastAPI backend scaffold with PostgreSQL and Redis.

## 🚀 Tech Stack

- **Framework**: FastAPI (Python 3.11)
- **Database**: PostgreSQL 15
- **Cache**: Redis 7
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Alembic
- **Validation**: Pydantic v2
- **Server**: Uvicorn

## 📁 Project Structure

```
heliox-ai/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI application entry point
│   │   └── core/
│   │       ├── config.py        # Environment & settings management
│   │       ├── db.py            # Database connection & session
│   │       └── logging.py       # Structured logging setup
│   ├── alembic/                 # Database migration scripts
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   ├── alembic.ini              # Alembic configuration
│   ├── requirements.txt         # Python dependencies
│   └── Dockerfile               # Container image definition
├── docker-compose.yml           # Multi-service orchestration
└── README.md                    # This file
```

## 🏃 Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+ (for local development without Docker)

### Running with Docker (Recommended)

1. **Start all services**:
   ```bash
   docker-compose up -d
   ```

2. **Check service health**:
   ```bash
   # API health
   curl http://localhost:8000/health
   
   # Database health
   curl http://localhost:8000/health/db
   ```

3. **View logs**:
   ```bash
   docker-compose logs -f api
   ```

4. **Stop services**:
   ```bash
   docker-compose down
   ```

### Running Locally (Without Docker)

1. **Install dependencies**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Start PostgreSQL and Redis** (using Docker):
   ```bash
   docker-compose up -d postgres redis
   ```

3. **Set environment variables**:
   ```bash
   export DATABASE_URL="postgresql+psycopg2://heliox:heliox_password@localhost:5432/heliox_db"
   export REDIS_URL="redis://localhost:6379/0"
   export ENV="development"
   export LOG_LEVEL="INFO"
   ```

4. **Run the application**:
   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Access the API**:
   - API: http://localhost:8000
   - Interactive docs: http://localhost:8000/docs
   - Alternative docs: http://localhost:8000/redoc

## 🗄️ Database Migrations

Heliox uses Alembic for database schema migrations with SQLAlchemy 2.0.

### Quick Commands

```bash
# Create a new migration (auto-generates from model changes)
make migration MSG="description of changes"

# Apply all pending migrations
make migrate

# Rollback one migration
make migrate-down

# View migration history
docker-compose exec api alembic history --verbose

# View current migration
docker-compose exec api alembic current
```

### Manual Commands

```bash
# Create migration
docker-compose exec api alembic revision --autogenerate -m "description"

# Apply migrations
docker-compose exec api alembic upgrade head

# Rollback one migration
docker-compose exec api alembic downgrade -1

# View migration history
docker-compose exec api alembic history --verbose
```

### Models Overview

Current database schema includes:

**Teams** (`teams`)
- `id` (UUID, PK)
- `name` (String, unique, indexed)
- `created_at`, `updated_at` (timestamps)

**Jobs** (`jobs`)
- `id` (UUID, PK)
- `team_id` (UUID, FK → teams)
- `model_name` (String)
- `gpu_type` (String)
- `provider` (String)
- `start_time`, `end_time` (timestamps, nullable)
- `status` (String)
- `created_at`, `updated_at` (timestamps)
- Indexes: team_id, (team_id, status), (provider, gpu_type), start_time

**Cost Snapshots** (`cost_snapshots`)
- `id` (UUID, PK)
- `date` (Date)
- `provider` (String)
- `gpu_type` (String)
- `cost_usd` (Decimal 12,2)
- `created_at`, `updated_at` (timestamps)
- Indexes: date, (date, provider, gpu_type)

**Usage Snapshots** (`usage_snapshots`)
- `id` (UUID, PK)
- `date` (Date)
- `provider` (String)
- `gpu_type` (String)
- `gpu_hours` (Decimal 12,2)
- `created_at`, `updated_at` (timestamps)
- Indexes: date, (date, provider, gpu_type)

### Migration Workflow

1. **Modify models** in `backend/app/models/`
2. **Generate migration**: `make migration MSG="your description"`
3. **Review migration** file in `backend/alembic/versions/`
4. **Apply migration**: `make migrate`
5. **Verify** in database: `make db-shell` → `\dt` → `\d table_name`

## 🔧 Configuration

Configuration is managed through environment variables. See `backend/.env.example` for available options.

### Key Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENV` | Environment (development/staging/production) | `development` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |
| `DATABASE_URL` | PostgreSQL connection string | See .env.example |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379/0` |
| `CORS_ENABLED` | Enable CORS middleware | `true` |
| `CORS_ORIGINS` | Allowed CORS origins (JSON array) | `["http://localhost:3000"]` |

## 📊 API Endpoints

### Health Checks

- `GET /health` - Basic health check
- `GET /health/db` - Database connection health check
- `GET /` - API information

### Documentation

- `GET /docs` - Swagger UI (interactive API documentation)
- `GET /redoc` - ReDoc (alternative API documentation)

## 🧪 Testing

```bash
cd backend
pytest
```

Run with coverage:
```bash
pytest --cov=app --cov-report=html
```

## 📝 Logging

The application uses structured logging with the following fields:
- `timestamp` - ISO format timestamp
- `level` - Log level (INFO, WARNING, ERROR, etc.)
- `request_id` - Unique request identifier
- `logger` - Logger name
- `message` - Log message

Example log output:
```
timestamp=2024-01-09T10:30:45 level=INFO logger=app.main message=Starting Heliox-AI in development environment request_id=550e8400-e29b-41d4-a716-446655440000
```

## 🔐 Security Features

- Non-root Docker user
- Input validation with Pydantic
- Global exception handling
- SQL injection protection via SQLAlchemy
- CORS configuration
- Connection pooling with health checks

## 🚢 Production Deployment

### Environment Setup

1. Set `ENV=production`
2. Use strong passwords for PostgreSQL
3. Configure proper `CORS_ORIGINS`
4. Set up SSL/TLS termination (reverse proxy)
5. Enable monitoring and alerting
6. Configure backup strategy for PostgreSQL

### Scaling Considerations

- Run multiple API instances behind a load balancer
- Use managed PostgreSQL (RDS, Cloud SQL, etc.)
- Use managed Redis (ElastiCache, Redis Cloud, etc.)
- Implement rate limiting
- Add authentication & authorization
- Set up centralized logging

## 📦 Development

### Code Quality

Format code:
```bash
black backend/app
```

Lint code:
```bash
ruff check backend/app
```

Type checking:
```bash
mypy backend/app
```

## 📖 Next Steps

1. **Add Authentication**: Implement JWT or OAuth2
2. **Add Models**: Create SQLAlchemy models for your domain
3. **Add Business Logic**: Implement services and repositories
4. **Add Tests**: Write unit and integration tests
5. **Add Monitoring**: Integrate Prometheus, Grafana, or Sentry
6. **Add Documentation**: Expand API documentation

## 🤝 Contributing

This is a production-ready scaffold. Extend it based on your specific requirements.

## 📄 License

MIT License - See LICENSE file for details

---

**Built with ❤️ for production-grade applications**

