# 🚀 Getting Started with Heliox-AI

## 📍 You Are Here

Your application is **running and healthy**!

- **API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs ← Currently open!
- **Health Check:** http://localhost:8000/health
- **DB Health:** http://localhost:8000/health/db

---

## 🎯 What You See in Swagger UI

The interactive API documentation shows:

### Current Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | API information |
| `/health` | GET | Basic health check |
| `/health/db` | GET | Database health check |

**Try it now:** Click on any endpoint → "Try it out" → "Execute"

---

## 📝 Your First API in 5 Minutes

### Quick Commands

```bash
# 1. Create directories
mkdir -p backend/app/models backend/app/schemas backend/app/api

# 2. Create model file
cat > backend/app/models/item.py << 'EOF'
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.core.db import Base

class Item(Base):
    __tablename__ = "items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
EOF

# 3. Create schema file
cat > backend/app/schemas/item.py << 'EOF'
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class ItemCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: Optional[str] = None

class Item(ItemCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True
EOF

# 4. Create API router
cat > backend/app/api/items.py << 'EOF'
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.item import Item
from app.schemas.item import ItemCreate, Item as ItemSchema

router = APIRouter(prefix="/items", tags=["Items"])

@router.get("/", response_model=List[ItemSchema])
def list_items(db: Session = Depends(get_db)):
    """List all items."""
    return db.query(Item).all()

@router.post("/", response_model=ItemSchema, status_code=status.HTTP_201_CREATED)
def create_item(item: ItemCreate, db: Session = Depends(get_db)):
    """Create a new item."""
    db_item = Item(**item.model_dump())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item
EOF

# 5. Create __init__ files
touch backend/app/models/__init__.py
touch backend/app/schemas/__init__.py
touch backend/app/api/__init__.py

# 6. Register router (add to backend/app/main.py)
# Add this line after imports:
# from app.api import items
# Add this line after CORS middleware:
# app.include_router(items.router, prefix="/api/v1")

# 7. Create migration
docker-compose exec api alembic revision --autogenerate -m "add items table"
docker-compose exec api alembic upgrade head

# 8. Test!
curl -X POST http://localhost:8000/api/v1/items \
  -H "Content-Type: application/json" \
  -d '{"name":"My First Item","description":"It works!"}'

curl http://localhost:8000/api/v1/items
```

---

## 🔄 Development Workflow

### 1. Make Changes
Edit any file in `backend/app/` - the app **auto-reloads**!

### 2. Watch Logs
```bash
make logs
# or
docker-compose logs -f api
```

### 3. Database Changes
```bash
# After adding/modifying models:
make migration MSG="description of change"
make migrate
```

### 4. Test in Swagger
Refresh http://localhost:8000/docs - your new endpoints appear automatically!

---

## 💡 Common Tasks

### Connect to Database
```bash
make db-shell
# Inside psql:
\dt          # List tables
\d items     # Describe items table
SELECT * FROM items;
```

### Connect to Redis
```bash
make redis-shell
# Inside redis-cli:
KEYS *       # List all keys
```

### View All Services
```bash
docker-compose ps
```

### Restart API (if needed)
```bash
docker-compose restart api
```

### Stop Everything
```bash
make stop
# or
docker-compose down
```

---

## 📚 Full Documentation

| Document | Purpose |
|----------|---------|
| `README.md` | Complete project guide |
| `QUICK_START.md` | Quick reference (most useful) |
| `ARCHITECTURE.md` | Technical deep-dive |
| `TEST_RESULTS.md` | Verified test results |

---

## 🎨 Swagger UI Tips

**In the browser (http://localhost:8000/docs):**

1. **Expand an endpoint** - Click on any endpoint bar
2. **Try it out** - Click the "Try it out" button
3. **Fill parameters** - Enter test data
4. **Execute** - Click "Execute" to make the request
5. **See response** - View the actual API response

**Useful for:**
- Testing endpoints without curl
- Seeing request/response schemas
- Generating example code
- Sharing API docs with team

---

## ⚡ Pro Tips

1. **Hot Reload**: Just save files - no restart needed!
2. **Type Safety**: Pydantic validates all requests automatically
3. **Auto Docs**: Swagger updates as you add endpoints
4. **DB Sessions**: Use `Depends(get_db)` - it's auto-managed
5. **Error Handling**: Raise `HTTPException` for proper errors

---

## 🐛 Troubleshooting

### API not responding?
```bash
docker-compose ps       # Check if running
docker-compose logs api # Check for errors
docker-compose restart api
```

### Database error?
```bash
make db-shell           # Connect to verify DB is up
make migrate           # Ensure migrations are applied
```

### Port already in use?
```bash
lsof -i :8000          # Find what's using port 8000
# Change port in docker-compose.yml if needed
```

---

## 🎯 Next Steps

1. ✅ **Explore Swagger UI** (already open!)
2. 📝 **Create your first endpoint** (follow guide above)
3. 🧪 **Test in Swagger UI**
4. 🔄 **Add more endpoints**
5. 🚀 **Build your application**

---

## 📞 Quick Reference

```bash
# Start
make start

# View logs
make logs

# Create migration
make migration MSG="your message"

# Apply migrations
make migrate

# Shell access
make shell          # API container
make db-shell       # PostgreSQL
make redis-shell    # Redis

# Health check
make health

# Stop
make stop
```

---

**Current Status:** ✅ **All Systems Operational**

**Your API is live at:** http://localhost:8000

**Swagger UI is at:** http://localhost:8000/docs

**Ready to build!** 🚀

