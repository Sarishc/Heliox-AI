#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"
ADMIN_API_KEY="${ADMIN_API_KEY:?ADMIN_API_KEY required - set from backend .env}"
TEAM_NAME="${TEAM_NAME:-Acme AI}"
KEY_NAME="${KEY_NAME:-Founder key}"

curl -s -X POST "${API_BASE_URL}/api/v1/admin/onboard" \
  -H "X-API-Key: ${ADMIN_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{\"team_name\":\"${TEAM_NAME}\",\"api_key_name\":\"${KEY_NAME}\"}"
