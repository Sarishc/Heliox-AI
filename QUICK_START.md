# 🚀 Heliox-AI Quick Start

## TL;DR

```bash
# Start everything
make start

# Check health
curl http://localhost:8000/health

# View docs
open http://localhost:8000/docs

# View logs
make logs

# Stop everything
make stop
```

---

## 🎯 One-Command Start

```bash
bash scripts/start-dev.sh
```

This will:
- ✅ Check Docker is running
- ✅ Create `.env` file
- ✅ Start all services
- ✅ Wait for health checks
- ✅ Show service URLs

---

## 📋 Essential Commands

### Start & Stop
```bash
make start          # Start all services
make stop           # Stop all services
make restart        # Restart all services
make clean          # Stop and remove volumes
```

### Development
```bash
make logs           # Follow API logs
make shell          # Open API shell
make db-shell       # Open PostgreSQL shell
make redis-shell    # Open Redis CLI
```

### Database
```bash
make migration MSG="add users table"  # Create migration
make migrate                          # Apply migrations
make migrate-down                     # Rollback migration
```

### Code Quality
```bash
make lint           # Run linter
make format         # Format code
make test           # Run tests
```

### Health Check
```bash
make health         # Check all services
make status         # Show service status
```

---

## 🌐 Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| API | http://localhost:8000 | Main API endpoint |
| API Docs | http://localhost:8000/docs | Swagger UI |
| ReDoc | http://localhost:8000/redoc | Alternative docs |
| PostgreSQL | localhost:5432 | Database |
| Redis | localhost:6379 | Cache |

---

## 🔌 API Endpoints

```bash
# Health checks
GET /health         # {"status":"ok"}
GET /health/db      # Database connection check

# Info
GET /               # API information

# Documentation
GET /docs           # Swagger UI
GET /redoc          # ReDoc
```

---

## 🗄️ Database Access

### PostgreSQL
```bash
# Via Docker
make db-shell

# Direct connection
psql -h localhost -p 5432 -U heliox -d heliox_db
# Password: heliox_password
```

### Redis
```bash
# Via Docker
make redis-shell

# Direct connection
redis-cli -h localhost -p 6379
```

---

## 🔧 Environment Variables

Copy and edit `.env`:
```bash
cd backend
cp .env.example .env
# Edit .env with your settings
```

Key variables:
```bash
ENV=development                 # Environment
LOG_LEVEL=INFO                 # Log level
DATABASE_URL=postgresql+...    # Database connection
REDIS_URL=redis://...          # Redis connection
CORS_ORIGINS=[...]             # Allowed origins
```

---

## 📝 Create Your First Feature

### 1. Create Model
```python
# backend/app/models/item.py
from sqlalchemy import Column, Integer, String
from app.core.db import Base

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, index=True)
```

### 2. Create Migration
```bash
make migration MSG="add items table"
make migrate
```

### 3. Create Schema
```python
# backend/app/schemas/item.py
from pydantic import BaseModel

class ItemCreate(BaseModel):
    name: str

class Item(ItemCreate):
    id: int
    class Config:
        from_attributes = True
```

### 4. Create Route
```python
# backend/app/api/items.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.models.item import Item
from app.schemas.item import ItemCreate, Item as ItemSchema

router = APIRouter()

@router.get("/items", response_model=list[ItemSchema])
def list_items(db: Session = Depends(get_db)):
    return db.query(Item).all()

@router.post("/items", response_model=ItemSchema)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    db_item = Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
```

### 5. Register Router
```python
# backend/app/main.py
from app.api import items

app.include_router(
    items.router,
    prefix="/api/v1",
    tags=["items"]
)
```

### 6. Test It
```bash
# Restart API to load changes
make restart

# Create item
curl -X POST http://localhost:8000/api/v1/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Item"}'

# List items
curl http://localhost:8000/api/v1/items
```

---

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Find process using port
lsof -i :8000
lsof -i :5432
lsof -i :6379

# Stop services first
make stop
```

### Services Won't Start
```bash
# Check Docker
docker info

# View logs
docker-compose logs

# Rebuild
make rebuild
```

### Database Connection Error
```bash
# Check PostgreSQL
docker-compose ps postgres

# Check DATABASE_URL
docker-compose exec api env | grep DATABASE_URL

# Restart PostgreSQL
docker-compose restart postgres
```

### Migration Issues
```bash
# Check current revision
docker-compose exec api alembic current

# View history
docker-compose exec api alembic history

# Downgrade and retry
make migrate-down
make migrate
```

---

## 📚 Documentation

- **README.md** - Complete project guide
- **ARCHITECTURE.md** - Technical architecture
- **SETUP_VERIFICATION.md** - Verification checklist
- **PROJECT_SUMMARY.md** - Feature overview
- **QUICK_START.md** - This file

---

## 🎓 Learning Resources

### FastAPI
- [Official Docs](https://fastapi.tiangolo.com/)
- [Tutorial](https://fastapi.tiangolo.com/tutorial/)

### SQLAlchemy
- [Official Docs](https://docs.sqlalchemy.org/)
- [ORM Quick Start](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)

### Pydantic
- [Official Docs](https://docs.pydantic.dev/)
- [Settings Management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)

### Docker
- [Official Docs](https://docs.docker.com/)
- [Compose](https://docs.docker.com/compose/)

---

## 💡 Tips

1. **Use Makefile** - It's faster: `make start` vs `docker-compose up -d`
2. **Check logs first** - Most issues show up in logs: `make logs`
3. **Hot reload works** - Edit code and see changes without restart
4. **Use /docs** - Swagger UI is your friend for testing
5. **Read error messages** - They're informative with request IDs

---

## 🎯 What's Next?

- [ ] Add authentication (JWT/OAuth2)
- [ ] Create your domain models
- [ ] Write unit tests
- [ ] Add API versioning
- [ ] Implement caching
- [ ] Add background tasks
- [ ] Set up monitoring
- [ ] Deploy to production

---

**Need help?** Check the full documentation in README.md

**Ready to build?** Run `make start` and start coding! 🚀

