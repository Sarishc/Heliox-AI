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
HOST="http://localhost:8000"

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
    echo "   cd /Users/sarish/Downloads/Projects/Heliox-AI"
    echo "   docker-compose up -d"
    exit 1
fi
echo "✅ Backend is healthy"
echo ""

# Install dependencies
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

echo "📦 Installing dependencies..."
source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "========================================="
echo "Starting load test in 5 seconds..."
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

echo ""
echo "========================================="
echo "✅ LOAD TEST COMPLETED"
echo "========================================="
echo ""
echo "📊 Results:"
echo "   - Locust Report: load-test/results/locust_report.html"
echo "   - Metrics: load-test/results/metrics_*.json"
echo "   - Summary: load-test/results/summary_*.txt"
echo "   - Monitor Log: load-test/results/monitor.log"
echo ""
echo "To view the HTML report:"
echo "   open load-test/results/locust_report.html"
echo ""
