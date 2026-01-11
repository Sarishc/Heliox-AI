#!/bin/bash
# Demo setup script for Heliox-AI
# Starts Docker, applies migrations, and seeds demo data

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
ADMIN_API_KEY="heliox-admin-key-change-in-production"
API_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

echo -e "${BLUE}🚀 Heliox-AI Demo Setup${NC}"
echo "=================================="
echo ""

# Step 1: Check prerequisites
echo -e "${BLUE}📋 Checking prerequisites...${NC}"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker is not running${NC}"
    echo "Please start Docker Desktop"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo -e "${RED}❌ Error: Docker Compose is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose is available${NC}"

echo ""

# Step 2: Create .env file if needed
echo -e "${BLUE}⚙️  Setting up environment...${NC}"
if [ ! -f backend/.env ]; then
    if [ -f backend/.env.example ]; then
        cp backend/.env.example backend/.env
        echo -e "${GREEN}✅ Created backend/.env from .env.example${NC}"
    else
        echo -e "${YELLOW}⚠️  Warning: backend/.env.example not found${NC}"
    fi
else
    echo -e "${GREEN}✅ backend/.env already exists${NC}"
fi
echo ""

# Step 3: Start Docker services
echo -e "${BLUE}🐳 Starting Docker services...${NC}"
docker-compose up -d

echo ""
echo -e "${YELLOW}⏳ Waiting for services to be ready...${NC}"

# Wait for PostgreSQL
echo -n "   - PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U postgres -d heliox > /dev/null 2>&1 || docker-compose exec -T postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo -e " ${GREEN}✓${NC}"

# Wait for Redis
echo -n "   - Redis..."
until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo -e " ${GREEN}✓${NC}"

# Wait for API
echo -n "   - API..."
max_attempts=60
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if curl -s -f "${API_URL}/health" > /dev/null 2>&1; then
        echo -e " ${GREEN}✓${NC}"
        break
    fi
    echo -n "."
    sleep 1
    attempt=$((attempt + 1))
done

if [ $attempt -eq $max_attempts ]; then
    echo -e " ${RED}✗${NC}"
    echo -e "${RED}❌ Error: API did not start in time${NC}"
    echo "Check logs with: docker-compose logs api"
    exit 1
fi

echo ""

# Step 4: Run migrations
echo -e "${BLUE}🗄️  Running database migrations...${NC}"
if docker-compose exec -T api alembic upgrade head > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Migrations applied successfully${NC}"
else
    echo -e "${YELLOW}⚠️  Warning: Migration command had issues (this may be normal if already up to date)${NC}"
fi
echo ""

# Step 5: Seed demo data
echo -e "${BLUE}🌱 Seeding demo data...${NC}"
SEED_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "${API_URL}/api/v1/admin/demo/seed" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -H "Content-Type: application/json" 2>&1)

HTTP_CODE=$(echo "$SEED_RESPONSE" | tail -n 1)
BODY=$(echo "$SEED_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ Demo data seeded successfully${NC}"
    # Extract and show summary if available
    if command -v python3 &> /dev/null; then
        echo "$BODY" | python3 -m json.tool 2>/dev/null | grep -E "(status|message|teams|jobs|cost_snapshots)" | head -10 || true
    fi
else
    echo -e "${RED}❌ Error seeding data (HTTP ${HTTP_CODE})${NC}"
    echo "Response: $BODY"
    exit 1
fi
echo ""

# Step 6: Verify setup
echo -e "${BLUE}🔍 Verifying setup...${NC}"
if curl -s -f "${API_URL}/health" > /dev/null; then
    echo -e "${GREEN}✅ API is healthy${NC}"
else
    echo -e "${RED}❌ API health check failed${NC}"
    exit 1
fi

if curl -s -f "${API_URL}/api/v1/admin/demo/status" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Demo endpoint is accessible${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Demo setup complete!${NC}"
echo ""
echo -e "${BLUE}📋 Service URLs:${NC}"
echo "   - Backend API:     ${API_URL}"
echo "   - API Docs:        ${API_URL}/docs"
echo "   - Frontend:        ${FRONTEND_URL} (start with: cd frontend && npm install && npm run dev)"
echo ""
echo -e "${BLUE}🎯 Next Steps:${NC}"
echo "   1. Start the frontend (if not already running):"
echo "      cd frontend && npm install && npm run dev"
echo ""
echo "   2. Open the dashboard in your browser:"
echo "      ${FRONTEND_URL}"
echo ""
echo "   3. Review DEMO.md for the complete demo script"
echo ""
echo -e "${BLUE}📊 Useful Commands:${NC}"
echo "   - View logs:        docker-compose logs -f api"
echo "   - Stop services:    docker-compose down"
echo "   - Reset demo data:  curl -X POST ${API_URL}/api/v1/admin/demo/seed -H \"X-API-Key: ${ADMIN_API_KEY}\""
echo ""
