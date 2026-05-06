#!/bin/bash
set -euo pipefail
# Creates all SSM Parameter Store secrets for Heliox.
# Safe to re-run — uses --overwrite for generated secrets only;
# placeholder values will NOT overwrite if already set.

REGION="us-east-1"

echo "=== Step 3: Creating SSM secrets ==="

# Load endpoints created in previous steps
source /tmp/heliox_env 2>/dev/null || true

# ── Helper: put param only if missing ────────────────────────────────────────
put_if_missing() {
  local name="$1"
  local value="$2"
  if aws ssm get-parameter --name "$name" --region "$REGION" &>/dev/null; then
    echo "  $name already exists — skipping"
  else
    aws ssm put-parameter \
      --region "$REGION" \
      --name "$name" \
      --value "$value" \
      --type SecureString > /dev/null
    echo "  Created: $name"
  fi
}

# ── Helper: put param always (generated secrets) ─────────────────────────────
put_always() {
  local name="$1"
  local value="$2"
  aws ssm put-parameter \
    --region "$REGION" \
    --name "$name" \
    --value "$value" \
    --type SecureString \
    --overwrite > /dev/null
  echo "  Set: $name"
}

# ── Generated secrets (always create/rotate) ─────────────────────────────────
echo ""
echo "Generating application secrets..."

SECRET_KEY=$(openssl rand -hex 32)
put_always "/heliox/SECRET_KEY" "$SECRET_KEY"

ADMIN_API_KEY=$(openssl rand -hex 32)
put_always "/heliox/ADMIN_API_KEY" "$ADMIN_API_KEY"

# Fernet key for OAuth token encryption
INTEGRATIONS_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null \
  || python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
put_always "/heliox/INTEGRATIONS_ENCRYPTION_KEY" "$INTEGRATIONS_KEY"

# ── Database URL (from step 1) ────────────────────────────────────────────────
echo ""
echo "Setting database connection..."

if [[ -n "${DATABASE_URL:-}" ]]; then
  put_always "/heliox/DATABASE_URL" "$DATABASE_URL"
else
  echo "  WARNING: DATABASE_URL not found in /tmp/heliox_env"
  echo "  Run 01_create_database.sh first, or set manually:"
  echo "    aws ssm put-parameter --name /heliox/DATABASE_URL --value 'postgresql+psycopg2://...' --type SecureString --region $REGION"
fi

# ── Redis URL (from step 2) ───────────────────────────────────────────────────
echo ""
echo "Setting Redis connection..."

if [[ -n "${REDIS_URL:-}" ]]; then
  put_always "/heliox/REDIS_URL" "$REDIS_URL"
else
  echo "  WARNING: REDIS_URL not found in /tmp/heliox_env"
  echo "  Run 02_create_redis.sh first, or set manually:"
  echo "    aws ssm put-parameter --name /heliox/REDIS_URL --value 'redis://...' --type SecureString --region $REGION"
fi

# ── Placeholder secrets (only create if missing — user fills in real values) ─
echo ""
echo "Creating placeholder secrets (edit these with real values)..."

put_if_missing "/heliox/STRIPE_SECRET_KEY"       "sk_live_REPLACE_ME"
put_if_missing "/heliox/STRIPE_WEBHOOK_SECRET"   "whsec_REPLACE_ME"
put_if_missing "/heliox/STRIPE_PRICE_ID_STARTER" "price_REPLACE_ME_STARTER"
put_if_missing "/heliox/STRIPE_PRICE_ID_GROWTH"  "price_REPLACE_ME_GROWTH"
put_if_missing "/heliox/GOOGLE_CLIENT_ID"        "REPLACE_ME.apps.googleusercontent.com"
put_if_missing "/heliox/GOOGLE_CLIENT_SECRET"    "REPLACE_ME"
put_if_missing "/heliox/SENTRY_DSN"              ""
put_if_missing "/heliox/SLACK_WEBHOOK_URL"       ""

# ── Print summary ─────────────────────────────────────────────────────────────
echo ""
echo "=== Step 3 complete: SSM secrets ==="
echo ""
echo "All parameters stored in SSM (us-east-1):"
aws ssm describe-parameters \
  --region "$REGION" \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/heliox/" \
  --query 'Parameters[*].{Name:Name,Type:Type,Modified:LastModifiedDate}' \
  --output table

echo ""
echo "IMPORTANT — update these placeholders with real values before launch:"
echo "  aws ssm put-parameter --name /heliox/STRIPE_SECRET_KEY     --value 'sk_live_...' --type SecureString --overwrite --region $REGION"
echo "  aws ssm put-parameter --name /heliox/STRIPE_WEBHOOK_SECRET --value 'whsec_...'   --type SecureString --overwrite --region $REGION"
echo "  aws ssm put-parameter --name /heliox/GOOGLE_CLIENT_ID      --value 'xxx.apps...' --type SecureString --overwrite --region $REGION"
echo "  aws ssm put-parameter --name /heliox/GOOGLE_CLIENT_SECRET  --value '...'         --type SecureString --overwrite --region $REGION"
echo ""
echo "Admin API key (save this!):"
echo "  $ADMIN_API_KEY"
