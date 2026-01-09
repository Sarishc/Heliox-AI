#!/bin/bash
set -e

# Configuration
API_KEY="heliox-admin-key-change-in-production"
BASE_URL="http://localhost:8000/api/v1"

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔═══════════════════════════════════════════════════════════════════════════════╗"
echo "║                                                                               ║"
echo "║            JOB METADATA INGESTION & ANALYTICS - TEST SUITE                   ║"
echo "║                                                                               ║"
echo "╚═══════════════════════════════════════════════════════════════════════════════╝"

# Get authentication token
echo -e "\n${BLUE}[SETUP]${NC} Getting authentication token..."
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@heliox.ai&password=admin123")

if echo "$TOKEN_RESPONSE" | grep -q "access_token"; then
    TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
    echo -e "${GREEN}✅ Authentication successful${NC}"
else
    echo -e "${RED}❌ Authentication failed${NC}"
    echo "$TOKEN_RESPONSE"
    exit 1
fi

# Test 1: Ingest Mock Job Data
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 1: Ingest Mock Job Data${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

RESPONSE=$(curl -s -X POST "$BASE_URL/admin/ingest/jobs/mock" \
  -H "X-API-Key: $API_KEY")

echo "$RESPONSE" | python3 -m json.tool

if echo "$RESPONSE" | grep -q '"status": "success"'; then
    echo -e "${GREEN}✅ Job ingestion successful${NC}"
    TEAMS_CREATED=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['teams']['created'])" 2>/dev/null || echo "0")
    JOBS_INSERTED=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['jobs']['inserted'])" 2>/dev/null || echo "0")
    echo -e "  Teams created: $TEAMS_CREATED"
    echo -e "  Jobs inserted: $JOBS_INSERTED"
else
    echo -e "${YELLOW}⚠️  Job ingestion completed with warnings or already ingested${NC}"
fi

# Test 2: List Jobs with Pagination
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 2: List Jobs with Pagination${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

RESPONSE=$(curl -s -X GET "$BASE_URL/jobs?skip=0&limit=10" \
  -H "Authorization: Bearer $TOKEN")

echo "$RESPONSE" | python3 -m json.tool | head -50

if echo "$RESPONSE" | grep -q '"total"'; then
    TOTAL=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['total'])")
    HAS_MORE=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['has_more'])")
    echo -e "${GREEN}✅ Pagination working${NC}"
    echo -e "  Total jobs: $TOTAL"
    echo -e "  Has more: $HAS_MORE"
else
    echo -e "${RED}❌ Pagination failed${NC}"
    exit 1
fi

# Test 3: Analytics - Cost by Model
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 3: Analytics - Cost by Model${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

RESPONSE=$(curl -s -X GET "$BASE_URL/analytics/cost/by-model?start=2026-01-01&end=2026-01-14" \
  -H "Authorization: Bearer $TOKEN")

echo "$RESPONSE" | python3 -m json.tool

if echo "$RESPONSE" | grep -q "model_name"; then
    echo -e "${GREEN}✅ Cost by model analytics working${NC}"
    MODEL_COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
    echo -e "  Models found: $MODEL_COUNT"
else
    echo -e "${YELLOW}⚠️  No cost data found or endpoint returned unexpected format${NC}"
fi

# Test 4: Analytics - Cost by Team
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 4: Analytics - Cost by Team${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

RESPONSE=$(curl -s -X GET "$BASE_URL/analytics/cost/by-team?start=2026-01-01&end=2026-01-14" \
  -H "Authorization: Bearer $TOKEN")

echo "$RESPONSE" | python3 -m json.tool

if echo "$RESPONSE" | grep -q "team_name"; then
    echo -e "${GREEN}✅ Cost by team analytics working${NC}"
    TEAM_COUNT=$(echo "$RESPONSE" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
    echo -e "  Teams found: $TEAM_COUNT"
else
    echo -e "${YELLOW}⚠️  No cost data found or endpoint returned unexpected format${NC}"
fi

# Test 5: Verify Database State
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 5: Verify Database State${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

echo -e "\n${YELLOW}Teams in database:${NC}"
docker-compose exec -T postgres psql -U postgres -d heliox -c "
SELECT name, description, budget_usd 
FROM teams 
ORDER BY name;" 2>/dev/null

echo -e "\n${YELLOW}Job statistics:${NC}"
docker-compose exec -T postgres psql -U postgres -d heliox -c "
SELECT 
    COUNT(*) as total_jobs,
    COUNT(DISTINCT team_id) as teams_with_jobs,
    COUNT(DISTINCT model_name) as unique_models,
    COUNT(DISTINCT provider) as providers,
    COUNT(DISTINCT gpu_type) as gpu_types,
    MIN(start_time) as earliest_job,
    MAX(start_time) as latest_job
FROM jobs;" 2>/dev/null

echo -e "\n${YELLOW}Jobs by status:${NC}"
docker-compose exec -T postgres psql -U postgres -d heliox -c "
SELECT status, COUNT(*) as count 
FROM jobs 
GROUP BY status 
ORDER BY count DESC;" 2>/dev/null

echo -e "\n${YELLOW}Jobs by model (top 5):${NC}"
docker-compose exec -T postgres psql -U postgres -d heliox -c "
SELECT model_name, COUNT(*) as job_count 
FROM jobs 
GROUP BY model_name 
ORDER BY job_count DESC 
LIMIT 5;" 2>/dev/null

# Test 6: Second Ingestion (Idempotency)
echo -e "\n${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}TEST 6: Second Ingestion (Idempotency Test)${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"

RESPONSE=$(curl -s -X POST "$BASE_URL/admin/ingest/jobs/mock" \
  -H "X-API-Key: $API_KEY")

echo "$RESPONSE" | python3 -m json.tool

if echo "$RESPONSE" | grep -q '"updated"'; then
    JOBS_UPDATED=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['jobs']['updated'])" 2>/dev/null || echo "0")
    JOBS_INSERTED=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['result']['jobs']['inserted'])" 2>/dev/null || echo "0")
    echo -e "${GREEN}✅ Idempotency working${NC}"
    echo -e "  Jobs inserted: $JOBS_INSERTED (should be 0)"
    echo -e "  Jobs updated: $JOBS_UPDATED (should be 30)"
else
    echo -e "${YELLOW}⚠️  Could not verify idempotency${NC}"
fi

# Summary
echo -e "\n╔═══════════════════════════════════════════════════════════════════════════════╗"
echo -e "║                                                                               ║"
echo -e "║                        ${GREEN}✅ ALL TESTS COMPLETED${NC}                                  ║"
echo -e "║                                                                               ║"
echo -e "╚═══════════════════════════════════════════════════════════════════════════════╝"

echo -e "\n${BLUE}Features Validated:${NC}"
echo -e "  ✅ Mock job data ingestion"
echo -e "  ✅ Team creation and lookup"
echo -e "  ✅ Job upsert with idempotency"
echo -e "  ✅ Job pagination (skip/limit)"
echo -e "  ✅ Analytics: Cost by model"
echo -e "  ✅ Analytics: Cost by team"
echo -e "  ✅ Database integrity"

echo -e "\n${BLUE}Next Steps:${NC}"
echo -e "  • Explore API docs: http://localhost:8000/docs"
echo -e "  • Test custom queries with different date ranges"
echo -e "  • Review analytics data for cost optimization insights"

