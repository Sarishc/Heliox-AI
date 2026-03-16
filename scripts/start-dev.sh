#!/bin/bash
# Quick start script for development environment

set -e

echo "🚀 Starting Heliox-AI Development Environment"
echo "=============================================="
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Error: Docker is not running. Please start Docker first."
    exit 1
fi

echo "✅ Docker is running"
echo ""

# Create .env file if it doesn't exist
if [ ! -f backend/.env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp backend/.env.example backend/.env
    echo "SECRET_KEY=dev-$(openssl rand -hex 32)" >> backend/.env
    echo "ADMIN_API_KEY=dev-admin-$(openssl rand -hex 24)" >> backend/.env
    echo "✅ Generated SECRET_KEY and ADMIN_API_KEY"
elif ! grep -q '^SECRET_KEY=.' backend/.env 2>/dev/null; then
    echo "⚠️  Adding SECRET_KEY to .env (required)"
    echo "SECRET_KEY=dev-$(openssl rand -hex 32)" >> backend/.env
    echo "ADMIN_API_KEY=dev-admin-$(openssl rand -hex 24)" >> backend/.env
fi

echo "🐳 Starting Docker containers..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 5

# Wait for PostgreSQL
echo "   - Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U heliox -d heliox_db > /dev/null 2>&1; do
    echo "      PostgreSQL is starting up..."
    sleep 2
done
echo "   ✅ PostgreSQL is ready"

# Wait for Redis
echo "   - Waiting for Redis..."
until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    echo "      Redis is starting up..."
    sleep 2
done
echo "   ✅ Redis is ready"

# Wait for API
echo "   - Waiting for API..."
sleep 3
until curl -s http://localhost:8000/health > /dev/null; do
    echo "      API is starting up..."
    sleep 2
done
echo "   ✅ API is ready"

echo ""
echo "🎉 All services are running!"
echo ""
echo "📋 Service URLs:"
echo "   - API:              http://localhost:8000"
echo "   - API Docs:         http://localhost:8000/docs"
echo "   - Health Check:     http://localhost:8000/health"
echo "   - DB Health Check:  http://localhost:8000/health/db"
echo "   - PostgreSQL:       localhost:5432"
echo "   - Redis:            localhost:6379"
echo ""
echo "📊 View logs:"
echo "   docker-compose logs -f api"
echo ""
echo "🛑 Stop services:"
echo "   docker-compose down"
echo ""

