#!/bin/bash
set -e

echo "========================================="
echo "🚀 HELIOX PERFORMANCE & LOAD TEST"
echo "========================================="
echo ""

# Configuration
USERS=100
SPAWN_RATE=10  # 10 users/second
DURATION=300   # 5 minutes
HOST="${HELIOX_HOST:-http://localhost:8000}"
ADMIN_API_KEY="${HELIOX_ADMIN_API_KEY:-dev-admin-key-change-me}"

echo "Configuration:"
echo "  Users: $USERS concurrent"
echo "  Spawn Rate: $SPAWN_RATE users/sec"
echo "  Duration: $DURATION seconds"
echo "  Target: $HOST"
echo ""

# Check if backend is running
echo "🔍 Checking backend health..."
if ! curl -s "$HOST/health" > /dev/null; then
    echo "❌ Backend is not responding at $HOST"
    echo "   Please start the backend first:"
    echo "   cd $(dirname "$0")/.."
    echo "   docker-compose up -d"
    exit 1
fi
echo "✅ Backend is healthy"
echo ""

# Seed demo data and create LoadTest API key for load testing
echo "🌱 Seeding demo data with LoadTest API key..."
SEED_RESPONSE=$(curl -s -X POST "${HOST}/api/v1/admin/demo/seed?create_load_test_key=true" \
    -H "X-API-Key: ${ADMIN_API_KEY}" \
    -H "Content-Type: application/json" 2>&1)
API_KEY=$(echo "$SEED_RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('load_test_api_key', ''))
except: print('')
" 2>/dev/null || true)
if [ -n "$API_KEY" ]; then
    export HELIOX_LOAD_TEST_API_KEY="$API_KEY"
    export HELIOX_ADMIN_API_KEY="$ADMIN_API_KEY"
    echo "✅ LoadTest API key created"
else
    echo "⚠️  No load_test_api_key in seed response - using env HELIOX_LOAD_TEST_API_KEY if set"
fi
echo ""

# Install dependencies
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

# Ensure results directory exists
mkdir -p results

echo ""
echo "========================================="
echo "Starting load test in 5 seconds..."
echo "Target: 100 users, ~500 req/min, 5 min"
echo "Press Ctrl+C to stop"
echo "========================================="
sleep 5

# Start system monitor in background
echo "🔍 Starting system monitor..."
python monitor.py $DURATION > results/monitor.log 2>&1 &
MONITOR_PID=$!
echo "   Monitor PID: $MONITOR_PID"

# Run Locust load test
echo ""
echo "🚀 Starting Locust load test..."
echo ""

locust \
    --headless \
    --users $USERS \
    --spawn-rate $SPAWN_RATE \
    --run-time ${DURATION}s \
    --host $HOST \
    --csv results/locust \
    --html results/locust_report.html \
    --loglevel INFO

# Wait for monitor to finish
echo ""
echo "⏳ Waiting for monitor to finish collecting metrics..."
wait $MONITOR_PID

# Generate load test report (PASS/FAIL vs targets)
echo ""
echo "📋 Generating load test report..."
python generate_report.py

echo ""
echo "========================================="
echo "✅ LOAD TEST COMPLETED"
echo "========================================="
echo ""
echo "📊 Results:"
echo "   - Report: load-test/results/load_test_report.txt"
echo "   - Locust Report: load-test/results/locust_report.html"
echo "   - Metrics: load-test/results/metrics_*.json"
echo "   - Summary: load-test/results/summary_*.txt"
echo "   - Monitor Log: load-test/results/monitor.log"
echo ""
echo "To view the HTML report:"
echo "   open load-test/results/locust_report.html"
echo ""
echo "For production load test, use 2 workers:"
echo "   docker compose -f docker-compose.yml -f docker-compose.loadtest.yml up -d"
echo ""
