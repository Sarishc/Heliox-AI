# Heliox-AI Database Models Documentation

## Overview

Heliox uses **SQLAlchemy 2.0** with typed ORM patterns (`Mapped[]`, `mapped_column`) for type safety and better IDE support.

---

## 📊 Database Schema

### Entity Relationship Diagram

```
┌─────────────┐
│   Teams     │
│─────────────│
│ id (PK)     │──┐
│ name        │  │
│ created_at  │  │
│ updated_at  │  │
└─────────────┘  │
                 │ 1:N
                 │
┌─────────────┐  │
│    Jobs     │  │
│─────────────│  │
│ id (PK)     │  │
│ team_id (FK)│──┘
│ model_name  │
│ gpu_type    │
│ provider    │
│ start_time  │
│ end_time    │
│ status      │
│ created_at  │
│ updated_at  │
└─────────────┘

┌──────────────────┐     ┌──────────────────┐
│  CostSnapshot    │     │  UsageSnapshot   │
│──────────────────│     │──────────────────│
│ id (PK)          │     │ id (PK)          │
│ date             │     │ date             │
│ provider         │     │ provider         │
│ gpu_type         │     │ gpu_type         │
│ cost_usd         │     │ gpu_hours        │
│ created_at       │     │ created_at       │
│ updated_at       │     │ updated_at       │
└──────────────────┘     └──────────────────┘
```

---

## 📝 Models

### Base Classes

#### `Base`
```python
from app.models.base import Base
```
SQLAlchemy 2.0 declarative base for all models.

#### `UUIDMixin`
```python
from app.models.base import UUIDMixin
```
Provides UUID primary key:
- `id`: UUID (auto-generated)

#### `TimestampMixin`
```python
from app.models.base import TimestampMixin
```
Provides automatic timestamps:
- `created_at`: Auto-set on creation
- `updated_at`: Auto-updated on modification

---

### Team Model

**File:** `backend/app/models/team.py`

**Table:** `teams`

**Purpose:** Represents a team/organization that owns jobs.

**Fields:**
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `name` | String(255) | UNIQUE, NOT NULL, INDEXED | Team name |
| `created_at` | Timestamp | NOT NULL | Creation time |
| `updated_at` | Timestamp | NOT NULL | Last update time |

**Relationships:**
- `jobs`: One-to-Many → Job (cascade delete)

**Indexes:**
- Primary key on `id`
- Unique index on `name`

**Usage Example:**
```python
from sqlalchemy.orm import Session
from app.models.team import Team

# Create a team
team = Team(name="Data Science Team")
db.add(team)
db.commit()

# Query teams
teams = db.query(Team).all()
team = db.query(Team).filter(Team.name == "Data Science Team").first()

# Access jobs
for job in team.jobs:
    print(job.model_name)
```

---

### Job Model

**File:** `backend/app/models/job.py`

**Table:** `jobs`

**Purpose:** Tracks individual GPU job executions.

**Fields:**
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `team_id` | UUID | FK → teams, NOT NULL, INDEXED | Owner team |
| `model_name` | String(255) | NOT NULL | ML model name |
| `gpu_type` | String(100) | NOT NULL | GPU type (A100, H100, etc.) |
| `provider` | String(100) | NOT NULL | Cloud provider (AWS, GCP, etc.) |
| `start_time` | Timestamp | NULLABLE | Job start time |
| `end_time` | Timestamp | NULLABLE | Job end time |
| `status` | String(50) | NOT NULL, DEFAULT='pending' | Job status |
| `created_at` | Timestamp | NOT NULL | Creation time |
| `updated_at` | Timestamp | NOT NULL | Last update time |

**Relationships:**
- `team`: Many-to-One → Team

**Indexes:**
- Primary key on `id`
- Index on `team_id`
- Composite index on `(team_id, status)`
- Composite index on `(provider, gpu_type)`
- Index on `start_time`

**Common Queries:**
```python
from sqlalchemy.orm import Session
from app.models.job import Job
from datetime import datetime

# Create a job
job = Job(
    team_id=team.id,
    model_name="llama-2-70b",
    gpu_type="A100",
    provider="AWS",
    status="pending"
)
db.add(job)
db.commit()

# Query jobs by team
team_jobs = db.query(Job).filter(Job.team_id == team_id).all()

# Query running jobs
running = db.query(Job).filter(Job.status == "running").all()

# Query by provider and GPU
aws_a100_jobs = db.query(Job).filter(
    Job.provider == "AWS",
    Job.gpu_type == "A100"
).all()

# Query jobs in date range
jobs_today = db.query(Job).filter(
    Job.start_time >= datetime.utcnow().date()
).all()
```

---

### CostSnapshot Model

**File:** `backend/app/models/cost.py`

**Table:** `cost_snapshots`

**Purpose:** Stores daily cost data per provider and GPU type.

**Fields:**
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `date` | Date | NOT NULL | Snapshot date |
| `provider` | String(100) | NOT NULL | Cloud provider |
| `gpu_type` | String(100) | NOT NULL | GPU type |
| `cost_usd` | Decimal(12,2) | NOT NULL | Cost in USD |
| `created_at` | Timestamp | NOT NULL | Creation time |
| `updated_at` | Timestamp | NOT NULL | Last update time |

**Indexes:**
- Primary key on `id`
- Index on `date`
- Composite index on `(date, provider, gpu_type)`

**Usage Example:**
```python
from app.models.cost import CostSnapshot
from datetime import date
from decimal import Decimal

# Create cost snapshot
snapshot = CostSnapshot(
    date=date.today(),
    provider="AWS",
    gpu_type="A100",
    cost_usd=Decimal("1250.50")
)
db.add(snapshot)
db.commit()

# Query costs by date
today_costs = db.query(CostSnapshot).filter(
    CostSnapshot.date == date.today()
).all()

# Query total cost for provider
from sqlalchemy import func
total_aws = db.query(
    func.sum(CostSnapshot.cost_usd)
).filter(
    CostSnapshot.provider == "AWS"
).scalar()

# Query costs for specific GPU type over time
a100_costs = db.query(CostSnapshot).filter(
    CostSnapshot.gpu_type == "A100"
).order_by(CostSnapshot.date.desc()).limit(30).all()
```

---

### UsageSnapshot Model

**File:** `backend/app/models/cost.py`

**Table:** `usage_snapshots`

**Purpose:** Stores daily GPU usage hours per provider and GPU type.

**Fields:**
| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| `id` | UUID | PK | Unique identifier |
| `date` | Date | NOT NULL | Snapshot date |
| `provider` | String(100) | NOT NULL | Cloud provider |
| `gpu_type` | String(100) | NOT NULL | GPU type |
| `gpu_hours` | Decimal(12,2) | NOT NULL | GPU hours used |
| `created_at` | Timestamp | NOT NULL | Creation time |
| `updated_at` | Timestamp | NOT NULL | Last update time |

**Indexes:**
- Primary key on `id`
- Index on `date`
- Composite index on `(date, provider, gpu_type)`

**Usage Example:**
```python
from app.models.cost import UsageSnapshot
from datetime import date
from decimal import Decimal

# Create usage snapshot
snapshot = UsageSnapshot(
    date=date.today(),
    provider="GCP",
    gpu_type="H100",
    gpu_hours=Decimal("240.5")
)
db.add(snapshot)
db.commit()

# Query usage by date range
from datetime import timedelta
week_ago = date.today() - timedelta(days=7)
weekly_usage = db.query(UsageSnapshot).filter(
    UsageSnapshot.date >= week_ago
).all()

# Calculate total hours per provider
from sqlalchemy import func
provider_hours = db.query(
    UsageSnapshot.provider,
    func.sum(UsageSnapshot.gpu_hours).label('total_hours')
).group_by(UsageSnapshot.provider).all()

# Find peak usage days
peak_days = db.query(
    UsageSnapshot.date,
    func.sum(UsageSnapshot.gpu_hours).label('total')
).group_by(UsageSnapshot.date).order_by(
    func.sum(UsageSnapshot.gpu_hours).desc()
).limit(10).all()
```

---

## 🔄 Migration Commands

### Create Migration
```bash
# After modifying models
make migration MSG="description of change"

# Or manually
docker-compose exec api alembic revision --autogenerate -m "description"
```

### Apply Migrations
```bash
# Apply all pending
make migrate

# Or manually
docker-compose exec api alembic upgrade head
```

### Rollback Migrations
```bash
# Rollback one
make migrate-down

# Or manually
docker-compose exec api alembic downgrade -1
```

### View Migration Status
```bash
# Current version
docker-compose exec api alembic current

# History
docker-compose exec api alembic history --verbose
```

---

## 🎯 Best Practices

### 1. Always Use Type Hints
```python
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[Optional[str]] = mapped_column(nullable=True)
```

### 2. Add Indexes for Query Patterns
```python
# Single column index
column: Mapped[str] = mapped_column(index=True)

# Composite index
__table_args__ = (
    Index('ix_model_date_provider', 'date', 'provider'),
)
```

### 3. Use Relationships Properly
```python
# One-to-Many
parent: Mapped["Parent"] = relationship(back_populates="children")
children: Mapped[List["Child"]] = relationship(back_populates="parent")
```

### 4. Add Meaningful Comments
```python
field: Mapped[str] = mapped_column(
    comment="Description of what this field represents"
)
```

### 5. Use Cascade Deletes
```python
team_id: Mapped[UUID] = mapped_column(
    ForeignKey("teams.id", ondelete="CASCADE")
)
```

---

## 🔍 Query Examples

### Complex Joins
```python
from sqlalchemy import select
from app.models import Team, Job

# Select with join
stmt = select(Team).join(Job).where(Job.status == "running")
teams_with_running_jobs = db.execute(stmt).scalars().all()
```

### Aggregations
```python
from sqlalchemy import func

# Count jobs per team
job_counts = db.query(
    Team.name,
    func.count(Job.id).label('job_count')
).join(Job).group_by(Team.name).all()
```

### Date Range Queries
```python
from datetime import datetime, timedelta

# Jobs in last 7 days
week_ago = datetime.utcnow() - timedelta(days=7)
recent_jobs = db.query(Job).filter(
    Job.start_time >= week_ago
).all()
```

---

## 📚 Resources

- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [FastAPI with SQLAlchemy](https://fastapi.tiangolo.com/tutorial/sql-databases/)

---

**Last Updated:** 2026-01-09  
**Schema Version:** 647fe0dac2a2

