# Heliox-AI API Implementation Guide

## 📚 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Authentication](#authentication)
4. [API Endpoints](#api-endpoints)
5. [Database Models](#database-models)
6. [CRUD Operations](#crud-operations)
7. [Testing](#testing)
8. [Deployment](#deployment)

---

## Overview

Heliox-AI is a production-grade GPU cost and usage tracking API built with:

- **FastAPI** - Modern, fast web framework
- **SQLAlchemy 2.0** - Async-ready ORM
- **PostgreSQL** - Reliable relational database
- **Redis** - High-performance caching
- **JWT Authentication** - Secure API access
- **Alembic** - Database migrations
- **Docker** - Containerized deployment

---

## Architecture

### Project Structure

```
heliox-ai/
├── backend/
│   ├── app/
│   │   ├── api/              # API endpoints
│   │   │   ├── auth.py       # Authentication
│   │   │   ├── teams.py      # Team management
│   │   │   ├── jobs.py       # Job tracking
│   │   │   ├── costs.py      # Cost snapshots
│   │   │   └── usage.py      # Usage snapshots
│   │   ├── auth/             # Authentication logic
│   │   │   ├── deps.py       # Dependencies
│   │   │   └── security.py   # JWT & password hashing
│   │   ├── core/             # Core configuration
│   │   │   ├── config.py     # Settings
│   │   │   ├── db.py         # Database setup
│   │   │   └── logging.py    # Structured logging
│   │   ├── crud/             # Database operations
│   │   ├── models/           # SQLAlchemy models
│   │   ├── schemas/          # Pydantic schemas
│   │   └── main.py           # Application entry
│   ├── alembic/              # Database migrations
│   ├── Dockerfile            # Container definition
│   └── requirements.txt      # Python dependencies
├── docker-compose.yml        # Service orchestration
└── test_api.sh              # End-to-end tests
```

### Components

1. **API Layer** (`app/api/`) - HTTP endpoints and request handling
2. **Business Logic** (`app/crud/`) - Database operations
3. **Data Models** (`app/models/`) - Database schema
4. **Validation** (`app/schemas/`) - Request/response validation
5. **Authentication** (`app/auth/`) - JWT token management

---

## Authentication

### JWT Token System

Heliox uses JWT (JSON Web Tokens) for stateless authentication.

#### Register a New User

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123",
    "full_name": "John Doe"
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_active": true,
  "created_at": "2026-01-09T20:00:00Z",
  "updated_at": "2026-01-09T20:00:00Z"
}
```

#### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=user@example.com&password=securepass123"
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

#### Using the Token

Include the token in the `Authorization` header:

```bash
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  http://localhost:8000/api/v1/teams/
```

---

## API Endpoints

### Base URL

```
http://localhost:8000
```

### Health Endpoints

#### GET /health

Basic health check.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok"
}
```

#### GET /health/db

Database connection health check.

```bash
curl http://localhost:8000/health/db
```

**Response:**
```json
{
  "status": "ok",
  "database": "connected",
  "message": "Database connection is healthy"
}
```

---

### Teams API

#### List Teams

**GET** `/api/v1/teams/`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/teams/?skip=0&limit=100"
```

#### Create Team

**POST** `/api/v1/teams/`

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Engineering Team"}' \
  http://localhost:8000/api/v1/teams/
```

#### Get Team

**GET** `/api/v1/teams/{team_id}`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/teams/{team_id}
```

#### Update Team

**PUT** `/api/v1/teams/{team_id}`

```bash
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Team Name"}' \
  http://localhost:8000/api/v1/teams/{team_id}
```

#### Delete Team

**DELETE** `/api/v1/teams/{team_id}`

```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/teams/{team_id}
```

---

### Jobs API

#### List Jobs

**GET** `/api/v1/jobs/`

Query parameters:
- `team_id` (UUID) - Filter by team
- `status` (string) - Filter by status
- `provider` (string) - Filter by cloud provider
- `skip` (int) - Pagination offset
- `limit` (int) - Items per page

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/jobs/?team_id={team_id}&status=running"
```

#### Create Job

**POST** `/api/v1/jobs/`

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "team_id": "550e8400-e29b-41d4-a716-446655440000",
    "model_name": "GPT-4",
    "gpu_type": "A100",
    "provider": "AWS",
    "status": "running",
    "start_time": "2026-01-09T20:00:00Z"
  }' \
  http://localhost:8000/api/v1/jobs/
```

#### Get Job

**GET** `/api/v1/jobs/{job_id}`

```bash
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/jobs/{job_id}
```

#### Update Job

**PUT** `/api/v1/jobs/{job_id}`

```bash
curl -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "completed",
    "end_time": "2026-01-09T22:00:00Z"
  }' \
  http://localhost:8000/api/v1/jobs/{job_id}
```

#### Delete Job

**DELETE** `/api/v1/jobs/{job_id}`

```bash
curl -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/jobs/{job_id}
```

---

### Cost Snapshots API

#### List Cost Snapshots

**GET** `/api/v1/costs/`

Query parameters:
- `start_date` (date) - Filter start date
- `end_date` (date) - Filter end date
- `provider` (string) - Filter by provider

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/costs/?start_date=2026-01-01&end_date=2026-01-31"
```

#### Create Cost Snapshot

**POST** `/api/v1/costs/`

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-01-09",
    "provider": "AWS",
    "gpu_type": "A100",
    "cost_usd": "150.50"
  }' \
  http://localhost:8000/api/v1/costs/
```

#### Get Total Cost

**GET** `/api/v1/costs/total`

Query parameters (required):
- `start_date` (date)
- `end_date` (date)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/costs/total?start_date=2026-01-01&end_date=2026-01-31"
```

**Response:**
```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "total_cost_usd": 4512.75
}
```

---

### Usage Snapshots API

#### List Usage Snapshots

**GET** `/api/v1/usage/`

Query parameters:
- `start_date` (date) - Filter start date
- `end_date` (date) - Filter end date
- `provider` (string) - Filter by provider

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/usage/?provider=AWS"
```

#### Create Usage Snapshot

**POST** `/api/v1/usage/`

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-01-09",
    "provider": "AWS",
    "gpu_type": "A100",
    "gpu_hours": "24.5"
  }' \
  http://localhost:8000/api/v1/usage/
```

#### Get Total Usage

**GET** `/api/v1/usage/total`

Query parameters (required):
- `start_date` (date)
- `end_date` (date)

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/usage/total?start_date=2026-01-01&end_date=2026-01-31"
```

**Response:**
```json
{
  "start_date": "2026-01-01",
  "end_date": "2026-01-31",
  "total_gpu_hours": 1247.5
}
```

---

## Database Models

### User

```python
- id: UUID (PK)
- email: String (unique, indexed)
- hashed_password: String
- full_name: String (nullable)
- is_active: Boolean
- created_at: DateTime
- updated_at: DateTime
```

### Team

```python
- id: UUID (PK)
- name: String (unique)
- created_at: DateTime
- updated_at: DateTime
```

### Job

```python
- id: UUID (PK)
- team_id: UUID (FK -> Team, CASCADE)
- model_name: String
- gpu_type: String (indexed)
- provider: String (indexed)
- start_time: DateTime (nullable)
- end_time: DateTime (nullable)
- status: String (indexed)
- created_at: DateTime
- updated_at: DateTime
```

### CostSnapshot

```python
- id: UUID (PK)
- date: Date (indexed)
- provider: String (indexed)
- gpu_type: String
- cost_usd: Decimal(12,2)
- created_at: DateTime
- updated_at: DateTime
```

### UsageSnapshot

```python
- id: UUID (PK)
- date: Date (indexed)
- provider: String (indexed)
- gpu_type: String
- gpu_hours: Decimal(12,2)
- created_at: DateTime
- updated_at: DateTime
```

---

## CRUD Operations

### Base CRUD Class

All CRUD operations inherit from `CRUDBase`:

```python
- get(db, id) - Get single record
- get_multi(db, skip, limit) - Get multiple records
- create(db, obj_in) - Create record
- update(db, db_obj, obj_in) - Update record
- delete(db, id) - Delete record
```

### Specialized Methods

#### Team CRUD
- `get_by_name(db, name)` - Find team by name

#### Job CRUD
- `get_by_team(db, team_id, skip, limit)` - Jobs by team
- `get_by_status(db, status, skip, limit)` - Jobs by status
- `get_by_provider(db, provider, skip, limit)` - Jobs by provider

#### Cost Snapshot CRUD
- `get_by_date_range(db, start_date, end_date)` - Costs by date
- `get_by_provider(db, provider, start_date, end_date)` - Costs by provider
- `get_total_cost(db, start_date, end_date)` - Sum of costs

#### Usage Snapshot CRUD
- `get_by_date_range(db, start_date, end_date)` - Usage by date
- `get_by_provider(db, provider, start_date, end_date)` - Usage by provider
- `get_total_hours(db, start_date, end_date)` - Sum of hours

#### User CRUD
- `get_by_email(db, email)` - Find user by email
- `authenticate(db, email, password)` - Verify credentials
- `is_active(user)` - Check if user is active

---

## Testing

### Run All Tests

```bash
./test_api.sh
```

### Manual Testing

#### 1. Start Services

```bash
docker-compose up --build
```

#### 2. Access Swagger UI

Open http://localhost:8000/docs in your browser for interactive API documentation.

#### 3. Test Authentication

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test12345","full_name":"Test User"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=test@example.com&password=test12345"
```

#### 4. Test Protected Endpoints

```bash
TOKEN="your_token_here"

# Create team
curl -X POST http://localhost:8000/api/v1/teams/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Team"}'
```

---

## Deployment

### Environment Variables

Create a `.env` file:

```env
# Application
APP_NAME=Heliox-AI
ENV=prod
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/heliox

# Redis
REDIS_URL=redis://redis:6379/0

# Security (CHANGE IN PRODUCTION!)
SECRET_KEY=your-super-secret-key-change-this

# CORS
CORS_ORIGINS=["https://yourdomain.com"]
```

### Production Deployment

1. **Update SECRET_KEY**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set Production Environment**
   ```env
   ENV=prod
   ```

3. **Configure CORS**
   ```env
   CORS_ORIGINS=["https://yourdomain.com", "https://app.yourdomain.com"]
   ```

4. **Use Strong Database Password**
   ```env
   DATABASE_URL=postgresql+psycopg2://user:strong_password@host:5432/dbname
   ```

5. **Deploy**
   ```bash
   docker-compose up -d
   ```

6. **Run Migrations**
   ```bash
   docker-compose exec api alembic upgrade head
   ```

### Health Monitoring

Monitor application health:

```bash
# Basic health
curl https://api.yourdomain.com/health

# Database health
curl https://api.yourdomain.com/health/db
```

---

## Additional Resources

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Spec**: http://localhost:8000/openapi.json

---

## Support

For issues, questions, or contributions, please refer to the project repository.

---

**Built with ❤️ using FastAPI, SQLAlchemy, and PostgreSQL**

