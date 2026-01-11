# Heliox-AI Architecture Documentation

## Overview

This document describes the architecture and design decisions for the Heliox-AI backend scaffold.

## Architecture Principles

### 1. Production-Grade from Day 1
- Structured logging with request ID tracking
- Global exception handling
- Health check endpoints
- Connection pooling
- Graceful shutdown handling

### 2. Separation of Concerns
- **Core**: Configuration, database, logging
- **API Layer**: Routes, request/response handling
- **Business Logic**: (To be added in domain-specific modules)
- **Data Layer**: SQLAlchemy models and repositories

### 3. Configuration Management
- Environment-based configuration
- Type-safe settings with Pydantic
- Validation at startup
- Cached settings instance

## Component Overview

### FastAPI Application (`app/main.py`)

**Responsibilities:**
- HTTP request handling
- Middleware registration
- Exception handling
- Route registration

**Key Features:**
- Async/await support
- Request ID middleware for tracing
- CORS middleware for cross-origin requests
- Lifespan management for startup/shutdown

### Configuration (`app/core/config.py`)

**Design:**
- Single source of truth for configuration
- Pydantic Settings for type safety
- Environment variable support with defaults
- LRU cache for singleton pattern

**Environment Variables:**
```python
ENV                 # development, staging, production
LOG_LEVEL          # DEBUG, INFO, WARNING, ERROR, CRITICAL
DATABASE_URL       # PostgreSQL connection string
REDIS_URL          # Redis connection string
CORS_ENABLED       # Enable/disable CORS
CORS_ORIGINS       # List of allowed origins
```

### Database (`app/core/db.py`)

**Design Patterns:**
- Repository pattern ready
- Dependency injection via FastAPI
- Connection pooling with health checks
- SQLAlchemy 2.0 async-ready design

**Connection Pool Settings:**
- Pool size: 5 connections
- Max overflow: 10 connections
- Pre-ping: Enabled (validates connections)
- Recycle: 3600 seconds (1 hour)

### Logging (`app/core/logging.py`)

**Features:**
- Structured logging (key=value format)
- Request ID propagation via context vars
- Configurable log levels
- Integration with Uvicorn

**Log Format:**
```
timestamp=<ISO8601> level=<LEVEL> logger=<NAME> message=<MSG> request_id=<UUID>
```

## API Endpoints

### Health Checks

#### `GET /health`
**Purpose:** Basic liveness check  
**Response:** `{"status": "ok"}`  
**Use Case:** Kubernetes liveness probe

#### `GET /health/db`
**Purpose:** Database readiness check  
**Response:** `{"status": "ok", "database": "connected", "message": "..."}`  
**Use Case:** Kubernetes readiness probe

#### `GET /`
**Purpose:** API information  
**Response:** `{"name": "...", "version": "...", "environment": "..."}`

## Database Migrations

### Alembic Configuration

**Structure:**
```
alembic/
├── env.py              # Migration environment
├── script.py.mako      # Migration template
└── versions/           # Migration files
```

**Workflow:**
1. Make model changes
2. Generate migration: `alembic revision --autogenerate -m "message"`
3. Review generated migration
4. Apply migration: `alembic upgrade head`

**Best Practices:**
- Always review auto-generated migrations
- Test migrations on a copy of production data
- Keep migrations reversible (implement downgrade)
- Never modify applied migrations

## Docker Architecture

### Services

#### API Service
- Multi-stage build for smaller image
- Non-root user for security
- Health checks built-in
- Volume mount for hot-reload in dev

#### PostgreSQL
- Alpine image for smaller size
- Persistent volume for data
- Health checks via pg_isready
- UTF-8 encoding by default

#### Redis
- Alpine image
- AOF persistence enabled
- Health checks via redis-cli ping

### Networking
- Bridge network for service communication
- Internal DNS resolution
- Port exposure for external access

## Error Handling

### Global Exception Handler
**Catches:** All unhandled exceptions  
**Returns:** Consistent JSON error response  
**Includes:** Request ID, error message, HTTP status

### Validation Error Handler
**Catches:** Pydantic validation errors  
**Returns:** Detailed validation error information  
**Status Code:** 422 Unprocessable Entity

### Error Response Format
```json
{
  "error": "Error type",
  "message": "Human-readable message",
  "request_id": "UUID",
  "details": {}  // Optional
}
```

## Security Considerations

### Implemented
- ✅ Non-root Docker user
- ✅ Input validation (Pydantic)
- ✅ SQL injection prevention (SQLAlchemy)
- ✅ CORS configuration
- ✅ Connection pool limits

### To Be Implemented
- 🔲 Authentication (JWT/OAuth2)
- 🔲 Authorization (RBAC)
- 🔲 Rate limiting
- 🔲 API key management
- 🔲 Request size limits
- 🔲 HTTPS enforcement
- 🔲 Security headers

## Scalability

### Current Design
- Stateless API (12-factor app)
- Horizontal scaling ready
- Connection pooling
- Redis for distributed caching

### Scaling Strategy
1. **Vertical Scaling**: Increase container resources
2. **Horizontal Scaling**: Multiple API instances + load balancer
3. **Database Scaling**: Read replicas, connection pooling
4. **Caching**: Redis for session/data caching

## Monitoring & Observability

### Implemented
- ✅ Structured logging
- ✅ Request ID tracing
- ✅ Health check endpoints

### Recommended Additions
- 🔲 Prometheus metrics endpoint
- 🔲 Distributed tracing (OpenTelemetry)
- 🔲 Error tracking (Sentry)
- 🔲 Performance monitoring (APM)
- 🔲 Log aggregation (ELK/Loki)

## Development Workflow

### Local Development
1. Start services: `make start` or `docker-compose up`
2. Make changes (hot-reload enabled)
3. Test changes
4. Run lints: `make lint`
5. Run tests: `make test`

### Adding New Features

#### 1. Add a new model
```python
# app/models/item.py
from sqlalchemy import Column, Integer, String
from app.core.db import Base

class Item(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
```

#### 2. Create migration
```bash
make migration MSG="add items table"
make migrate
```

#### 3. Add Pydantic schemas
```python
# app/schemas/item.py
from pydantic import BaseModel

class ItemBase(BaseModel):
    name: str

class ItemCreate(ItemBase):
    pass

class Item(ItemBase):
    id: int
    
    class Config:
        from_attributes = True
```

#### 4. Add routes
```python
# app/api/items.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db

router = APIRouter()

@router.get("/items")
def read_items(db: Session = Depends(get_db)):
    return []
```

#### 5. Register router
```python
# app/main.py
from app.api import items

app.include_router(items.router, prefix="/api/v1")
```

## Testing Strategy

### Unit Tests
- Test business logic in isolation
- Mock external dependencies
- Fast execution

### Integration Tests
- Test API endpoints
- Use test database
- Test database interactions

### Test Structure
```
tests/
├── unit/
│   ├── test_config.py
│   └── test_models.py
├── integration/
│   ├── test_api.py
│   └── test_db.py
└── conftest.py  # Pytest fixtures
```

## Deployment

### Environment Variables
Set in deployment environment (Kubernetes secrets, AWS Parameter Store, etc.)

### Database Migrations
Run migrations as part of deployment pipeline:
```bash
alembic upgrade head
```

### Health Checks
Configure container orchestrator:
- Liveness: `/health`
- Readiness: `/health/db`

### Resource Limits
Recommended starting points:
- **API**: 256MB RAM, 0.25 CPU
- **PostgreSQL**: 1GB RAM, 0.5 CPU
- **Redis**: 256MB RAM, 0.25 CPU

## Future Enhancements

### Near-term
- [ ] Authentication & authorization
- [ ] API versioning strategy
- [ ] Rate limiting
- [ ] Caching layer
- [ ] Background tasks (Celery/ARQ)

### Medium-term
- [ ] Multi-tenancy support
- [ ] GraphQL endpoint
- [ ] WebSocket support
- [ ] File upload handling
- [ ] Email notifications

### Long-term
- [ ] Microservices architecture
- [ ] Event-driven architecture
- [ ] CQRS pattern
- [ ] Multi-region deployment

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/)
- [Pydantic V2 Documentation](https://docs.pydantic.dev/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [12-Factor App Methodology](https://12factor.net/)

---

**Last Updated:** 2024-01-09  
**Version:** 0.1.0

