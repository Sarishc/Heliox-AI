# 🧪 Test Instructions

## Quick Test (3 commands)

```bash
# 1. Start services
docker-compose up --build

# 2. Test health endpoint (in new terminal)
curl localhost:8000/health

# 3. Test database health
curl localhost:8000/health/db
```

---

## Step-by-Step Testing

### Prerequisites
```bash
# Check Docker is running
docker info

# Check ports are available
lsof -i :8000  # Should be empty
lsof -i :5432  # Should be empty
lsof -i :6379  # Should be empty
```

---

### Test 1: Build and Start

```bash
docker-compose up --build
```

**What to expect:**
```
[+] Building backend
[+] Running 3/3
 ✔ Container heliox-postgres  Started
 ✔ Container heliox-redis     Started
 ✔ Container heliox-api       Started
```

**Wait for healthy status (~10-15 seconds):**
```
heliox-postgres  | database system is ready to accept connections
heliox-redis     | Ready to accept connections
heliox-api       | Application startup complete
```

**Verify in logs:**
- ✅ "Starting Heliox-AI in dev environment"
- ✅ "Log level: INFO"
- ✅ No error messages

---

### Test 2: Health Check (Fast)

**Open a new terminal:**
```bash
curl localhost:8000/health
```

**Expected response:**
```json
{"status":"ok"}
```

**Performance check:**
```bash
time curl localhost:8000/health
```
**Expected:** < 0.1 seconds

**What this tests:**
- ✅ API is running
- ✅ Responds quickly
- ✅ No database dependencies
- ✅ Suitable for liveness probe

---

### Test 3: Database Health Check

```bash
curl localhost:8000/health/db
```

**Expected response:**
```json
{
  "status": "ok",
  "database": "connected",
  "message": "Database connection is healthy"
}
```

**What this tests:**
- ✅ Database connection works
- ✅ Connection pool is healthy
- ✅ Can execute queries
- ✅ Returns meaningful message

---

### Test 4: Database Down Scenario

**Stop the database:**
```bash
docker-compose stop postgres
```

**Test the health endpoint:**
```bash
curl -i localhost:8000/health/db
```

**Expected response:**
```
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{
  "status": "error",
  "database": "disconnected",
  "message": "Database connection failed"
}
```

**What this tests:**
- ✅ Returns 503 status code
- ✅ Returns meaningful error message
- ✅ API doesn't crash when DB is down
- ✅ Suitable for readiness probe

**Restart the database:**
```bash
docker-compose start postgres
# Wait 5 seconds
sleep 5
curl localhost:8000/health/db
```

**Expected:** Should return "ok" again

---

### Test 5: API Documentation

```bash
# Test docs endpoint
curl -s localhost:8000/docs | grep -o "<title>.*</title>"
# Expected: <title>Heliox-AI - Swagger UI</title>

# Or open in browser
open http://localhost:8000/docs
```

**What to verify:**
- ✅ Swagger UI loads
- ✅ All endpoints listed
- ✅ Can test endpoints interactively
- ✅ Health endpoints visible

---

### Test 6: API Info

```bash
curl localhost:8000/
```

**Expected response:**
```json
{
  "name": "Heliox-AI",
  "version": "0.1.0",
  "environment": "dev"
}
```

---

### Test 7: Configuration

**Check environment variables:**
```bash
docker-compose exec api env | grep -E "DATABASE_URL|REDIS_URL|ENV"
```

**Expected:**
```
DATABASE_URL=postgresql+psycopg://postgres:postgres@postgres:5432/heliox
REDIS_URL=redis://redis:6379/0
ENV=dev
```

---

### Test 8: Database Connection

**Connect to PostgreSQL:**
```bash
docker-compose exec postgres psql -U postgres -d heliox
```

**Inside psql:**
```sql
-- Check connection
\conninfo
-- Expected: You are connected to database "heliox" as user "postgres"

-- List databases
\l
-- Should see "heliox" database

-- Quit
\q
```

---

### Test 9: Redis Connection

**Connect to Redis:**
```bash
docker-compose exec redis redis-cli
```

**Inside redis-cli:**
```
PING
# Expected: PONG

INFO server
# Should show Redis version info

exit
```

---

### Test 10: Logs

**View API logs:**
```bash
docker-compose logs api
```

**What to look for:**
- ✅ "Starting Heliox-AI in dev environment"
- ✅ "Log level: INFO"
- ✅ Structured log format (key=value)
- ✅ Request IDs in logs
- ✅ No error messages

**Follow logs in real-time:**
```bash
docker-compose logs -f api
```

---

### Test 11: Service Status

```bash
docker-compose ps
```

**Expected output:**
```
NAME               STATUS          PORTS
heliox-api         Up (healthy)    0.0.0.0:8000->8000/tcp
heliox-postgres    Up (healthy)    0.0.0.0:5432->5432/tcp
heliox-redis       Up (healthy)    0.0.0.0:6379->6379/tcp
```

**All services should show:**
- ✅ "Up" status
- ✅ "(healthy)" indicator
- ✅ Correct port mappings

---

### Test 12: Request ID Tracking

**Make a request and check headers:**
```bash
curl -i localhost:8000/health
```

**Look for header:**
```
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
```

**Custom request ID:**
```bash
curl -H "X-Request-ID: test-123" -i localhost:8000/health
```

**Expected:** Response should include `X-Request-ID: test-123`

---

## 🚀 Automated Test Script

Save this as `test.sh`:

```bash
#!/bin/bash
set -e

echo "🧪 Heliox-AI Test Suite"
echo "======================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

# Helper function
test_endpoint() {
    local name=$1
    local url=$2
    local expected=$3
    
    echo -n "Testing $name... "
    response=$(curl -s $url)
    
    if [[ $response == *"$expected"* ]]; then
        echo -e "${GREEN}PASS${NC}"
        ((PASSED++))
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Expected: $expected"
        echo "  Got: $response"
        ((FAILED++))
    fi
}

# Start services
echo "📦 Starting services..."
docker-compose up -d --build > /dev/null 2>&1

echo "⏳ Waiting for services to be healthy..."
sleep 15

echo ""
echo "Running tests..."
echo "----------------"

# Run tests
test_endpoint "/health" "http://localhost:8000/health" '"status":"ok"'
test_endpoint "/health/db (UP)" "http://localhost:8000/health/db" '"status":"ok"'
test_endpoint "/" "http://localhost:8000/" '"name":"Heliox-AI"'

# Test DB down
echo -n "Testing /health/db (DOWN)... "
docker-compose stop postgres > /dev/null 2>&1
sleep 3
response=$(curl -s http://localhost:8000/health/db)
if [[ $response == *'"status":"error"'* ]]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Restart DB
docker-compose start postgres > /dev/null 2>&1
sleep 5

# Test docs
echo -n "Testing /docs... "
status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs)
if [[ $status == "200" ]]; then
    echo -e "${GREEN}PASS${NC}"
    ((PASSED++))
else
    echo -e "${RED}FAIL${NC}"
    ((FAILED++))
fi

# Summary
echo ""
echo "======================="
echo "Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "======================="

if [ $FAILED -eq 0 ]; then
    echo "🎉 All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi
```

**Run it:**
```bash
chmod +x test.sh
./test.sh
```

---

## 🧹 Cleanup

**Stop services:**
```bash
docker-compose down
```

**Stop and remove volumes:**
```bash
docker-compose down -v
```

**Remove all (including images):**
```bash
docker-compose down -v --rmi all
```

---

## 🐛 Troubleshooting

### Port already in use
```bash
# Find process
lsof -i :8000
lsof -i :5432
lsof -i :6379

# Kill process
kill -9 <PID>
```

### Services not healthy
```bash
# Check logs
docker-compose logs

# Check specific service
docker-compose logs postgres
docker-compose logs redis
docker-compose logs api
```

### Database connection failed
```bash
# Restart PostgreSQL
docker-compose restart postgres

# Check PostgreSQL logs
docker-compose logs postgres

# Verify connection string
docker-compose exec api env | grep DATABASE_URL
```

### API not responding
```bash
# Check if API is running
docker-compose ps api

# Check API logs
docker-compose logs api

# Restart API
docker-compose restart api
```

---

## ✅ Expected Results Summary

| Test | Expected Result |
|------|----------------|
| Build | No errors, 3 services start |
| /health | `{"status":"ok"}` in < 100ms |
| /health/db (UP) | `{"status":"ok","database":"connected"}` |
| /health/db (DOWN) | 503 status, `{"status":"error"}` |
| /docs | Swagger UI loads |
| / | API info with name and version |
| Logs | Structured logs with timestamps |
| Service status | All services show "(healthy)" |

---

## 🎯 All Tests Pass Criteria

✅ All services start without errors  
✅ `/health` responds in < 100ms  
✅ `/health/db` returns ok when database is up  
✅ `/health/db` returns 503 when database is down  
✅ API documentation loads  
✅ All services show healthy status  
✅ Logs show no errors  
✅ Request IDs present in headers  
✅ Configuration uses correct values  

**If all tests pass:** ✅ **Production-ready scaffold is working correctly!**

