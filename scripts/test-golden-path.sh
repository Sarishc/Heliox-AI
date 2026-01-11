#!/bin/bash
# Golden Path End-to-End Test for Heliox MVP
# Tests the critical path that must work for YC demo

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
API_URL="http://localhost:8000"
ADMIN_API_KEY="${ADMIN_API_KEY:-heliox-admin-key-change-in-production}"
MAX_WAIT_TIME=60  # seconds
RETRY_INTERVAL=2  # seconds

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

log_error() {
    echo -e "${RED}[✗]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Wait for service to be healthy
wait_for_service() {
    local url=$1
    local service_name=$2
    local elapsed=0
    
    log_info "Waiting for ${service_name} to be ready..."
    
    while [ $elapsed -lt $MAX_WAIT_TIME ]; do
        if curl -sf "${url}" > /dev/null 2>&1; then
            log_success "${service_name} is ready"
            return 0
        fi
        sleep $RETRY_INTERVAL
        elapsed=$((elapsed + RETRY_INTERVAL))
        echo -n "."
    done
    
    log_error "${service_name} failed to become ready after ${MAX_WAIT_TIME}s"
    return 1
}

# Check API endpoint returns success
check_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local description=$4
    local auth_header=$5
    
    local curl_cmd="curl -sf -w '\n%{http_code}' -X ${method} '${API_URL}${endpoint}'"
    
    if [ -n "${auth_header}" ]; then
        curl_cmd="${curl_cmd} -H '${auth_header}'"
    fi
    
    local response=$(eval "${curl_cmd}" 2>&1)
    local http_code=$(echo "${response}" | tail -n1)
    local body=$(echo "${response}" | head -n-1)
    
    if [ "${http_code}" = "${expected_status}" ]; then
        log_success "${description}"
        return 0
    else
        log_error "${description} - Expected ${expected_status}, got ${http_code}"
        echo "Response: ${body}"
        return 1
    fi
}

# Test endpoint returns valid JSON with expected fields
check_json_endpoint() {
    local endpoint=$1
    local description=$2
    local expected_field=$3
    local auth_header=$4
    
    local curl_cmd="curl -sf -X GET '${API_URL}${endpoint}'"
    
    if [ -n "${auth_header}" ]; then
        curl_cmd="${curl_cmd} -H '${auth_header}'"
    fi
    
    local response=$(eval "${curl_cmd}" 2>&1)
    
    if [ $? -ne 0 ]; then
        log_error "${description} - Request failed"
        return 1
    fi
    
    # Check if response is valid JSON
    if ! echo "${response}" | python3 -m json.tool > /dev/null 2>&1; then
        log_error "${description} - Invalid JSON response"
        echo "Response: ${response}"
        return 1
    fi
    
    # Check for expected field (if provided)
    if [ -n "${expected_field}" ]; then
        if echo "${response}" | python3 -c "import sys, json; data = json.load(sys.stdin); sys.exit(0 if '${expected_field}' in data or isinstance(data, list) else 1)" 2>/dev/null; then
            log_success "${description}"
            return 0
        else
            log_error "${description} - Missing expected field: ${expected_field}"
            return 1
        fi
    else
        log_success "${description}"
        return 0
    fi
}

# Main test execution
main() {
    local failed_tests=0
    local total_tests=0
    
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║   Heliox MVP - Golden Path End-to-End Test                ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Prerequisites
    log_info "Checking prerequisites..."
    
    if ! command_exists docker; then
        log_error "Docker is not installed"
        exit 1
    fi
    
    if ! command_exists docker-compose; then
        log_error "docker-compose is not installed"
        exit 1
    fi
    
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    log_success "Prerequisites met"
    echo ""
    
    # Step 1: Start stack
    log_info "Step 1: Starting Docker stack..."
    if docker-compose up -d postgres redis > /dev/null 2>&1; then
        log_success "Docker stack started"
    else
        log_error "Failed to start Docker stack"
        exit 1
    fi
    
    # Wait for services
    sleep 3
    wait_for_service "http://localhost:5432" "PostgreSQL" || exit 1
    wait_for_service "http://localhost:6379" "Redis" || exit 1
    
    # Start API (if not already running)
    if ! docker-compose ps api | grep -q "Up"; then
        log_info "Starting API service..."
        docker-compose up -d api > /dev/null 2>&1
    fi
    
    echo ""
    
    # Step 2: Run migrations
    log_info "Step 2: Running database migrations..."
    if docker-compose exec -T api alembic upgrade head > /dev/null 2>&1; then
        log_success "Migrations applied"
    else
        log_error "Migrations failed"
        exit 1
    fi
    echo ""
    
    # Step 3: Wait for API
    log_info "Step 3: Waiting for API to be ready..."
    wait_for_service "${API_URL}/health" "API" || exit 1
    echo ""
    
    # Step 4: Seed mock data
    log_info "Step 4: Seeding mock data..."
    total_tests=$((total_tests + 1))
    if curl -sf -X POST "${API_URL}/api/v1/admin/demo/seed" \
        -H "X-API-Key: ${ADMIN_API_KEY}" \
        -H "Content-Type: application/json" > /dev/null 2>&1; then
        log_success "Mock data seeded"
        sleep 2  # Give DB time to commit
    else
        log_error "Failed to seed mock data"
        failed_tests=$((failed_tests + 1))
    fi
    echo ""
    
    # Step 5: Test endpoints (Golden Path)
    log_info "Step 5: Testing Golden Path endpoints..."
    echo ""
    
    # 5.1: Health check
    total_tests=$((total_tests + 1))
    if check_endpoint "GET" "/health" "200" "Health check"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.2: Database health
    total_tests=$((total_tests + 1))
    if check_endpoint "GET" "/health/db" "200" "Database health check"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.3: Spend trend (analytics endpoint - simplified test)
    total_tests=$((total_tests + 1))
    # Calculate date range (last 14 days) - macOS and Linux compatible
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        END_DATE=$(date +%Y-%m-%d)
        START_DATE=$(date -v-13d +%Y-%m-%d)
    else
        # Linux
        END_DATE=$(date +%Y-%m-%d)
        START_DATE=$(date -d "13 days ago" +%Y-%m-%d)
    fi
    
    if check_json_endpoint "/api/v1/analytics/cost/by-model?start=${START_DATE}&end=${END_DATE}" \
        "Spend trend (cost by model)" "model_name"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.4: Cost by team
    total_tests=$((total_tests + 1))
    if check_json_endpoint "/api/v1/analytics/cost/by-team?start=${START_DATE}&end=${END_DATE}" \
        "Cost by team" "team_name"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.5: Recommendations
    total_tests=$((total_tests + 1))
    if check_json_endpoint "/api/v1/recommendations?start_date=${START_DATE}&end_date=${END_DATE}" \
        "Recommendations" "recommendations"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.6: Forecast
    total_tests=$((total_tests + 1))
    if check_json_endpoint "/api/v1/forecast/spend?horizon_days=7" \
        "Forecast (spend)" "forecast"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    # 5.7: Daily digest (admin endpoint)
    total_tests=$((total_tests + 1))
    auth_header="X-API-Key: ${ADMIN_API_KEY}"
    if check_json_endpoint "/api/v1/daily-digest/" \
        "Daily digest" "total_daily_cost" "${auth_header}"; then
        :  # Success
    else
        failed_tests=$((failed_tests + 1))
    fi
    
    echo ""
    
    # Summary
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║   Test Summary                                             ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo ""
    
    local passed_tests=$((total_tests - failed_tests))
    echo "Total tests: ${total_tests}"
    echo -e "${GREEN}Passed: ${passed_tests}${NC}"
    
    if [ $failed_tests -gt 0 ]; then
        echo -e "${RED}Failed: ${failed_tests}${NC}"
        echo ""
        log_error "Golden Path test FAILED"
        echo ""
        log_info "To debug:"
        echo "  1. Check logs: docker-compose logs api"
        echo "  2. Check database: docker-compose exec postgres psql -U postgres -d heliox"
        echo "  3. Check API docs: ${API_URL}/docs"
        exit 1
    else
        echo ""
        log_success "Golden Path test PASSED"
        echo ""
        log_info "Next steps:"
        echo "  1. Open dashboard: http://localhost:3000"
        echo "  2. View API docs: ${API_URL}/docs"
        echo "  3. Test recommendations endpoint manually"
        exit 0
    fi
}

# Run main function
main "$@"
