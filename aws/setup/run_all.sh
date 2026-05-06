#!/bin/bash
set -euo pipefail
# Master setup script — deploys the full Heliox stack on AWS.
# Run from the aws/setup/ directory.
#
# Prerequisites:
#   1. AWS CLI configured (aws sts get-caller-identity should return your account)
#   2. Docker image already in ECR (run 00_create_codebuild.sh first, OR
#      push manually from GitHub Actions)
#   3. Run from: cd aws/setup && bash run_all.sh

ACCOUNT_ID="038462779905"
REGION="us-east-1"

echo ""
echo "╔═══════════════════════════════════════╗"
echo "║        Heliox AWS Setup               ║"
echo "║  Account : $ACCOUNT_ID           ║"
echo "║  Region  : $REGION                 ║"
echo "╚═══════════════════════════════════════╝"
echo ""

# ── Prerequisites ─────────────────────────────────────────────────────────────
echo "Checking prerequisites..."

command -v aws >/dev/null 2>&1 || { echo "ERROR: aws CLI not installed"; exit 1; }
command -v openssl >/dev/null 2>&1 || { echo "ERROR: openssl not installed"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not installed"; exit 1; }

aws sts get-caller-identity >/dev/null 2>&1 || { echo "ERROR: AWS not configured. Run: aws configure"; exit 1; }

# Check ECR image exists
if ! aws ecr describe-images \
    --repository-name "heliox" \
    --region "$REGION" \
    --image-ids imageTag=latest &>/dev/null; then
  echo ""
  echo "ERROR: No Docker image found in ECR (038462779905.dkr.ecr.us-east-1.amazonaws.com/heliox:latest)"
  echo ""
  echo "Build and push the image first:"
  echo "  bash 00_create_codebuild.sh"
  echo ""
  echo "Or build via GitHub Actions by pushing to main branch."
  exit 1
fi

echo "  All prerequisites met."
echo ""

# ── Initialize state file ─────────────────────────────────────────────────────
rm -f /tmp/heliox_env
touch /tmp/heliox_env

# ── Run each step ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_step() {
  local step="$1"
  local script="$2"
  echo ""
  echo "────────────────────────────────────────"
  echo " Running: $script"
  echo "────────────────────────────────────────"
  bash "${SCRIPT_DIR}/${script}"
  echo ""
  echo "✓ $step complete"
}

run_step "Database (RDS)"     "01_create_database.sh"
run_step "Cache (Redis)"      "02_create_redis.sh"
run_step "VPC Connector"      "06_create_vpc_connector.sh"
run_step "SSM Secrets"        "03_create_ssm_secrets.sh"
run_step "App Runner"         "04_create_apprunner.sh"
run_step "DB Migrations"      "05_run_migrations.sh"

# ── Final health check ────────────────────────────────────────────────────────
source /tmp/heliox_env 2>/dev/null || true

echo ""
echo "────────────────────────────────────────"
echo " Final health check"
echo "────────────────────────────────────────"

APP_URL="${APP_RUNNER_URL:-}"
if [[ -z "$APP_URL" ]]; then
  APP_URL=$(aws apprunner list-services \
    --region "$REGION" \
    --query "ServiceSummaryList[?ServiceName=='heliox'].ServiceUrl" \
    --output text 2>/dev/null)
  APP_URL="https://${APP_URL}"
fi

if [[ -n "$APP_URL" && "$APP_URL" != "https://" ]]; then
  echo "Testing: $APP_URL/health"
  for i in $(seq 1 12); do
    if curl -sf "${APP_URL}/health" >/dev/null 2>&1; then
      echo "  ✓ Health check passed"
      break
    fi
    echo "  Attempt $i/12 — waiting 10s..."
    sleep 10
  done
fi

echo ""
echo "╔═══════════════════════════════════════════════════════╗"
echo "║  🎉  Heliox is live!                                  ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo ""
echo "  App URL : $APP_URL"
echo "  Health  : ${APP_URL}/health"
echo "  API     : ${APP_URL}/api/v1/"
echo ""
echo "Next steps:"
echo "  1. Seed demo data:"
echo "     ADMIN_KEY=\$(aws ssm get-parameter --name /heliox/ADMIN_API_KEY --with-decryption --query Parameter.Value --output text --region $REGION)"
echo "     curl -X POST ${APP_URL}/api/v1/admin/demo/seed -H \"X-API-Key: \$ADMIN_KEY\""
echo ""
echo "  2. Set a custom domain in App Runner Console:"
echo "     AWS Console → App Runner → heliox → Custom domains"
echo ""
echo "  3. Update Stripe/Google placeholders in SSM:"
echo "     aws ssm put-parameter --name /heliox/STRIPE_SECRET_KEY --value 'sk_live_...' --type SecureString --overwrite --region $REGION"
echo ""
echo "  4. Every future deploy: push to GitHub main → auto-deploys via GitHub Actions"
