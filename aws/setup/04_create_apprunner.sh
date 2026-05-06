#!/bin/bash
set -euo pipefail
# Creates AWS App Runner service for Heliox.
# Pulls from ECR, reads secrets from SSM, exposes HTTPS on port 8000.

ACCOUNT_ID="038462779905"
REGION="us-east-1"
ECR_IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/heliox:latest"
SERVICE_NAME="heliox"
ACCESS_ROLE_NAME="heliox-apprunner-ecr-role"
INSTANCE_ROLE_NAME="heliox-apprunner-instance-role"

echo "=== Step 4: Creating App Runner service ==="

# ── Fetch secrets from SSM ────────────────────────────────────────────────────
echo "Fetching secrets from SSM..."

get_secret() {
  aws ssm get-parameter \
    --name "$1" \
    --with-decryption \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text 2>/dev/null || echo ""
}

SECRET_KEY=$(get_secret "/heliox/SECRET_KEY")
ADMIN_API_KEY=$(get_secret "/heliox/ADMIN_API_KEY")
INTEGRATIONS_KEY=$(get_secret "/heliox/INTEGRATIONS_ENCRYPTION_KEY")
DATABASE_URL=$(get_secret "/heliox/DATABASE_URL")
REDIS_URL=$(get_secret "/heliox/REDIS_URL")
STRIPE_SECRET_KEY=$(get_secret "/heliox/STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET=$(get_secret "/heliox/STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_GROWTH=$(get_secret "/heliox/STRIPE_PRICE_ID_GROWTH")
GOOGLE_CLIENT_ID=$(get_secret "/heliox/GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET=$(get_secret "/heliox/GOOGLE_CLIENT_SECRET")
SENTRY_DSN=$(get_secret "/heliox/SENTRY_DSN")
SLACK_WEBHOOK_URL=$(get_secret "/heliox/SLACK_WEBHOOK_URL")

# Validate required secrets
for var_name in SECRET_KEY ADMIN_API_KEY INTEGRATIONS_KEY DATABASE_URL REDIS_URL; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "ERROR: $var_name is empty. Run 03_create_ssm_secrets.sh first."
    exit 1
  fi
done

echo "  All required secrets fetched."

# ── IAM role: ECR access (allows App Runner to pull images) ──────────────────
if aws iam get-role --role-name "$ACCESS_ROLE_NAME" &>/dev/null; then
  echo "  ECR access role already exists — skipping"
else
  echo "Creating ECR access role..."
  aws iam create-role \
    --role-name "$ACCESS_ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' > /dev/null

  aws iam attach-role-policy \
    --role-name "$ACCESS_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"

  echo "  ECR access role created. Waiting for propagation..."
  sleep 10
fi

ACCESS_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ACCESS_ROLE_NAME}"

# ── IAM role: instance role (running container permissions) ──────────────────
if aws iam get-role --role-name "$INSTANCE_ROLE_NAME" &>/dev/null; then
  echo "  Instance role already exists — skipping"
else
  echo "Creating instance role..."
  aws iam create-role \
    --role-name "$INSTANCE_ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "tasks.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' > /dev/null

  aws iam put-role-policy \
    --role-name "$INSTANCE_ROLE_NAME" \
    --policy-name "heliox-instance-policy" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [
        {
          \"Effect\": \"Allow\",
          \"Action\": [\"ssm:GetParameter\", \"ssm:GetParameters\"],
          \"Resource\": \"arn:aws:ssm:${REGION}:${ACCOUNT_ID}:parameter/heliox/*\"
        },
        {
          \"Effect\": \"Allow\",
          \"Action\": [\"logs:CreateLogGroup\", \"logs:CreateLogStream\", \"logs:PutLogEvents\"],
          \"Resource\": \"arn:aws:logs:${REGION}:${ACCOUNT_ID}:log-group:/aws/apprunner/*\"
        }
      ]
    }"

  echo "  Instance role created. Waiting for propagation..."
  sleep 10
fi

INSTANCE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${INSTANCE_ROLE_NAME}"

# ── Check if App Runner service already exists ────────────────────────────────
EXISTING_ARN=$(aws apprunner list-services \
  --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
  --output text 2>/dev/null)

if [[ -n "$EXISTING_ARN" && "$EXISTING_ARN" != "None" ]]; then
  echo "  App Runner service already exists: $EXISTING_ARN"
  echo "  To redeploy with latest image, run:"
  echo "    aws apprunner start-deployment --service-arn $EXISTING_ARN --region $REGION"
  SERVICE_ARN="$EXISTING_ARN"
else
  echo "Creating App Runner service..."

  SERVICE_ARN=$(aws apprunner create-service \
    --region "$REGION" \
    --service-name "$SERVICE_NAME" \
    --source-configuration "{
      \"ImageRepository\": {
        \"ImageIdentifier\": \"${ECR_IMAGE}\",
        \"ImageRepositoryType\": \"ECR\",
        \"ImageConfiguration\": {
          \"Port\": \"8000\",
          \"StartCommand\": \"uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2\",
          \"RuntimeEnvironmentVariables\": {
            \"ENV\": \"production\",
            \"SECRET_KEY\": \"${SECRET_KEY}\",
            \"ADMIN_API_KEY\": \"${ADMIN_API_KEY}\",
            \"INTEGRATIONS_ENCRYPTION_KEY\": \"${INTEGRATIONS_KEY}\",
            \"DATABASE_URL\": \"${DATABASE_URL}\",
            \"REDIS_URL\": \"${REDIS_URL}\",
            \"STRIPE_SECRET_KEY\": \"${STRIPE_SECRET_KEY}\",
            \"STRIPE_WEBHOOK_SECRET\": \"${STRIPE_WEBHOOK_SECRET}\",
            \"STRIPE_PRICE_ID_GROWTH\": \"${STRIPE_PRICE_GROWTH}\",
            \"GOOGLE_CLIENT_ID\": \"${GOOGLE_CLIENT_ID}\",
            \"GOOGLE_CLIENT_SECRET\": \"${GOOGLE_CLIENT_SECRET}\",
            \"SENTRY_DSN\": \"${SENTRY_DSN}\",
            \"SLACK_WEBHOOK_URL\": \"${SLACK_WEBHOOK_URL}\",
            \"AUTH_COOKIE_SECURE\": \"true\",
            \"LOG_JSON_FORMAT\": \"true\",
            \"CORS_ENABLED\": \"true\"
          }
        }
      },
      \"AuthenticationConfiguration\": {
        \"AccessRoleArn\": \"${ACCESS_ROLE_ARN}\"
      },
      \"AutoDeploymentsEnabled\": false
    }" \
    --instance-configuration "{
      \"Cpu\": \"1024\",
      \"Memory\": \"2048\",
      \"InstanceRoleArn\": \"${INSTANCE_ROLE_ARN}\"
    }" \
    --health-check-configuration "{
      \"Protocol\": \"HTTP\",
      \"Path\": \"/health\",
      \"Interval\": 10,
      \"Timeout\": 5,
      \"HealthyThreshold\": 1,
      \"UnhealthyThreshold\": 3
    }" \
    --auto-scaling-configuration-arn "arn:aws:apprunner:${REGION}:${ACCOUNT_ID}:autoscalingconfiguration/DefaultConfiguration/1/00000000000000000000000000000001" \
    --query 'Service.ServiceArn' \
    --output text)

  echo "  Service ARN: $SERVICE_ARN"
fi

# Save ARN for subsequent scripts
echo "APP_RUNNER_ARN=$SERVICE_ARN" >> /tmp/heliox_env

# ── Wait for service to reach RUNNING state ───────────────────────────────────
echo ""
echo "Waiting for App Runner service to start (3-5 minutes)..."

while true; do
  STATUS=$(aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --region "$REGION" \
    --query 'Service.Status' \
    --output text)

  SERVICE_URL=$(aws apprunner describe-service \
    --service-arn "$SERVICE_ARN" \
    --region "$REGION" \
    --query 'Service.ServiceUrl' \
    --output text)

  echo "  Status: $STATUS"

  if [[ "$STATUS" == "RUNNING" ]]; then
    break
  elif [[ "$STATUS" == "CREATE_FAILED" || "$STATUS" == "DELETE_FAILED" ]]; then
    echo "ERROR: App Runner service failed with status: $STATUS"
    echo "Check logs in the AWS Console → App Runner → $SERVICE_NAME → Logs"
    exit 1
  fi

  sleep 15
done

# Save URL
echo "APP_RUNNER_URL=https://${SERVICE_URL}" >> /tmp/heliox_env

echo ""
echo "=== Step 4 complete: App Runner service is RUNNING ==="
echo "  Service ARN : $SERVICE_ARN"
echo "  URL         : https://${SERVICE_URL}"
echo ""
echo "  Health check: curl https://${SERVICE_URL}/health"
