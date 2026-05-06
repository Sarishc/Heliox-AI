#!/bin/bash
set -euo pipefail
# Runs `alembic upgrade head` against the production database.
# Uses a temporary Docker container on the local machine — OR runs directly
# if DATABASE_URL is accessible (e.g. via SSH tunnel or publicly-accessible RDS).
#
# Since RDS is NOT publicly accessible, this script runs migrations by
# temporarily starting a one-off ECS/Fargate task, or by using a jump host.
# The simplest approach at this stage: run from the App Runner task via the
# AWS CLI `apprunner start-deployment` (which rebuilds) — OR use an ECS
# run-task with the same image.
#
# This script uses the App Runner VPC Connector's subnet + SG to launch
# a short-lived Fargate task that can reach RDS.

ACCOUNT_ID="038462779905"
REGION="us-east-1"
ECR_IMAGE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/heliox:latest"

echo "=== Step 5: Running database migrations ==="

# Load environment from previous steps
source /tmp/heliox_env 2>/dev/null || true

# ── Check if DATABASE_URL is available ───────────────────────────────────────
if [[ -z "${DATABASE_URL:-}" ]]; then
  DATABASE_URL=$(aws ssm get-parameter \
    --name "/heliox/DATABASE_URL" \
    --with-decryption \
    --region "$REGION" \
    --query 'Parameter.Value' \
    --output text 2>/dev/null || echo "")
fi

if [[ -z "$DATABASE_URL" ]]; then
  echo "ERROR: DATABASE_URL not found. Run 01_create_database.sh and 03_create_ssm_secrets.sh first."
  exit 1
fi

# ── Get other required secrets ────────────────────────────────────────────────
SECRET_KEY=$(aws ssm get-parameter --name "/heliox/SECRET_KEY" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
ADMIN_API_KEY=$(aws ssm get-parameter --name "/heliox/ADMIN_API_KEY" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
INTEGRATIONS_KEY=$(aws ssm get-parameter --name "/heliox/INTEGRATIONS_ENCRYPTION_KEY" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)
REDIS_URL=$(aws ssm get-parameter --name "/heliox/REDIS_URL" --with-decryption --region "$REGION" --query 'Parameter.Value' --output text)

# ── Get VPC networking info ───────────────────────────────────────────────────
VPC_CONNECTOR_ARN="${VPC_CONNECTOR_ARN:-}"

# Use subnets and security group from VPC connector (set in step 6)
# For now use the same subnets as RDS
SUBNET_ID="subnet-0d132a65284861998"

# Get the App Runner VPC SG if it exists, else use the RDS SG
MIGRATION_SG="${VPC_CONNECTOR_SG_ID:-${RDS_SG_ID:-}}"

if [[ -z "$MIGRATION_SG" ]]; then
  MIGRATION_SG=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters "Name=group-name,Values=heliox-vpc-connector-sg" "Name=vpc-id,Values=vpc-0fe7c9eb87a51bc0e" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null)
fi

# ── Create ECS cluster for migration task (if needed) ────────────────────────
CLUSTER_NAME="heliox-migrations"

if ! aws ecs describe-clusters --clusters "$CLUSTER_NAME" --region "$REGION" \
    --query 'clusters[0].status' --output text 2>/dev/null | grep -q "ACTIVE"; then
  echo "Creating temporary ECS cluster for migrations..."
  aws ecs create-cluster --cluster-name "$CLUSTER_NAME" --region "$REGION" > /dev/null
fi

# ── Create ECS task execution role (if needed) ───────────────────────────────
EXEC_ROLE_NAME="heliox-migration-execution-role"

if ! aws iam get-role --role-name "$EXEC_ROLE_NAME" &>/dev/null; then
  echo "Creating ECS task execution role..."
  aws iam create-role \
    --role-name "$EXEC_ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ecs-tasks.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' > /dev/null

  aws iam attach-role-policy \
    --role-name "$EXEC_ROLE_NAME" \
    --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"

  aws iam put-role-policy \
    --role-name "$EXEC_ROLE_NAME" \
    --policy-name "ecr-pull" \
    --policy-document "{
      \"Version\": \"2012-10-17\",
      \"Statement\": [{
        \"Effect\": \"Allow\",
        \"Action\": [\"ecr:GetAuthorizationToken\", \"ecr:BatchCheckLayerAvailability\",
                     \"ecr:GetDownloadUrlForLayer\", \"ecr:BatchGetImage\"],
        \"Resource\": \"*\"
      }]
    }"

  sleep 10
fi

EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE_NAME}"

# ── Register migration task definition ───────────────────────────────────────
echo "Registering migration task definition..."

TASK_DEF_ARN=$(aws ecs register-task-definition \
  --region "$REGION" \
  --family "heliox-migration" \
  --network-mode awsvpc \
  --requires-compatibilities FARGATE \
  --cpu "512" \
  --memory "1024" \
  --execution-role-arn "$EXEC_ROLE_ARN" \
  --container-definitions "[{
    \"name\": \"migration\",
    \"image\": \"${ECR_IMAGE}\",
    \"command\": [\"alembic\", \"upgrade\", \"head\"],
    \"environment\": [
      {\"name\": \"DATABASE_URL\", \"value\": \"${DATABASE_URL}\"},
      {\"name\": \"SECRET_KEY\", \"value\": \"${SECRET_KEY}\"},
      {\"name\": \"ADMIN_API_KEY\", \"value\": \"${ADMIN_API_KEY}\"},
      {\"name\": \"INTEGRATIONS_ENCRYPTION_KEY\", \"value\": \"${INTEGRATIONS_KEY}\"},
      {\"name\": \"REDIS_URL\", \"value\": \"${REDIS_URL}\"},
      {\"name\": \"ENV\", \"value\": \"production\"},
      {\"name\": \"STRIPE_SECRET_KEY\", \"value\": \"sk_test_placeholder\"},
      {\"name\": \"STRIPE_WEBHOOK_SECRET\", \"value\": \"whsec_placeholder\"}
    ],
    \"logConfiguration\": {
      \"logDriver\": \"awslogs\",
      \"options\": {
        \"awslogs-group\": \"/ecs/heliox-migrations\",
        \"awslogs-region\": \"${REGION}\",
        \"awslogs-stream-prefix\": \"migration\",
        \"awslogs-create-group\": \"true\"
      }
    }
  }]" \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "  Task definition: $TASK_DEF_ARN"

# ── Run migration task ────────────────────────────────────────────────────────
NETWORK_CONFIG="{
  \"awsvpcConfiguration\": {
    \"subnets\": [\"${SUBNET_ID}\"],
    \"assignPublicIp\": \"ENABLED\"
  }
}"

if [[ -n "$MIGRATION_SG" && "$MIGRATION_SG" != "None" ]]; then
  NETWORK_CONFIG="{
    \"awsvpcConfiguration\": {
      \"subnets\": [\"${SUBNET_ID}\"],
      \"securityGroups\": [\"${MIGRATION_SG}\"],
      \"assignPublicIp\": \"ENABLED\"
    }
  }"
fi

echo "Running migration task..."
TASK_ARN=$(aws ecs run-task \
  --cluster "$CLUSTER_NAME" \
  --task-definition "$TASK_DEF_ARN" \
  --launch-type FARGATE \
  --network-configuration "$NETWORK_CONFIG" \
  --region "$REGION" \
  --query 'tasks[0].taskArn' \
  --output text)

echo "  Task ARN: $TASK_ARN"
echo "  Waiting for migration to complete..."

aws ecs wait tasks-stopped \
  --cluster "$CLUSTER_NAME" \
  --tasks "$TASK_ARN" \
  --region "$REGION"

# ── Check exit code ───────────────────────────────────────────────────────────
EXIT_CODE=$(aws ecs describe-tasks \
  --cluster "$CLUSTER_NAME" \
  --tasks "$TASK_ARN" \
  --region "$REGION" \
  --query 'tasks[0].containers[0].exitCode' \
  --output text)

STOP_REASON=$(aws ecs describe-tasks \
  --cluster "$CLUSTER_NAME" \
  --tasks "$TASK_ARN" \
  --region "$REGION" \
  --query 'tasks[0].stoppedReason' \
  --output text)

if [[ "$EXIT_CODE" == "0" ]]; then
  echo ""
  echo "=== Step 5 complete: Migrations ran successfully ==="
else
  echo ""
  echo "ERROR: Migration task exited with code $EXIT_CODE"
  echo "Reason: $STOP_REASON"
  echo ""
  echo "View logs:"
  echo "  aws logs tail /ecs/heliox-migrations --region $REGION"
  exit 1
fi
