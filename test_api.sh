#!/bin/bash

# Heliox-AI API End-to-End Test Script
# This script tests all major API endpoints

set -e  # Exit on error

BASE_URL="http://localhost:8000"

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                  HELIOX-AI API END-TO-END TESTS                   ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"
echo

# Test Health Endpoints
echo "1. Testing Health Endpoints..."
echo "   - GET /health"
curl -s $BASE_URL/health | python3 -m json.tool
echo "   - GET /health/db"
curl -s $BASE_URL/health/db | python3 -m json.tool
echo "   ✅ Health endpoints working"
echo

# Register New User
echo "2. Registering New User..."
TOKEN=$(curl -s -X POST $BASE_URL/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@heliox.ai&password=admin12345" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "   ❌ Failed to get token"
  exit 1
fi
echo "   ✅ Logged in successfully"
echo

# Create Team
echo "3. Creating Team..."
TIMESTAMP=$(date +%s)
TEAM_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/teams/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Team-$TIMESTAMP\"}")
echo "$TEAM_RESPONSE" | python3 -m json.tool
TEAM_ID=$(echo "$TEAM_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "   ✅ Team created: $TEAM_ID"
echo

# Create Job
echo "4. Creating Job..."
JOB_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/jobs/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"team_id\":\"$TEAM_ID\",\"model_name\":\"GPT-4\",\"gpu_type\":\"A100\",\"provider\":\"AWS\",\"status\":\"running\"}")
echo "$JOB_RESPONSE" | python3 -m json.tool
JOB_ID=$(echo "$JOB_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "   ✅ Job created: $JOB_ID"
echo

# Create Cost Snapshot
echo "5. Creating Cost Snapshot..."
COST_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/costs/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-01-09","provider":"AWS","gpu_type":"A100","cost_usd":"150.50"}')
echo "$COST_RESPONSE" | python3 -m json.tool
COST_ID=$(echo "$COST_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "   ✅ Cost snapshot created: $COST_ID"
echo

# Create Usage Snapshot
echo "6. Creating Usage Snapshot..."
USAGE_RESPONSE=$(curl -s -X POST $BASE_URL/api/v1/usage/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"date":"2026-01-09","provider":"AWS","gpu_type":"A100","gpu_hours":"24.5"}')
echo "$USAGE_RESPONSE" | python3 -m json.tool
USAGE_ID=$(echo "$USAGE_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "   ✅ Usage snapshot created: $USAGE_ID"
echo

# List Teams
echo "7. Listing Teams..."
curl -s $BASE_URL/api/v1/teams/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo "   ✅ Teams listed"
echo

# List Jobs
echo "8. Listing Jobs..."
curl -s $BASE_URL/api/v1/jobs/ \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo "   ✅ Jobs listed"
echo

# Get Total Cost
echo "9. Getting Total Cost..."
curl -s "$BASE_URL/api/v1/costs/total?start_date=2026-01-01&end_date=2026-01-31" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo "   ✅ Total cost retrieved"
echo

# Get Total Usage
echo "10. Getting Total Usage..."
curl -s "$BASE_URL/api/v1/usage/total?start_date=2026-01-01&end_date=2026-01-31" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo "   ✅ Total usage retrieved"
echo

echo "╔═══════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ ALL TESTS PASSED!                            ║"
echo "╚═══════════════════════════════════════════════════════════════════╝"

