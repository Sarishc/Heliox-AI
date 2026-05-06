#!/bin/bash
set -euo pipefail
# Creates App Runner VPC Connector so the service can reach RDS and Redis
# in the default VPC. Must run BEFORE 04_create_apprunner.sh, or re-run
# 04_create_apprunner.sh after this to update the service.

ACCOUNT_ID="038462779905"
REGION="us-east-1"
VPC_ID="vpc-0fe7c9eb87a51bc0e"
CONNECTOR_NAME="heliox-vpc-connector"
SG_NAME="heliox-vpc-connector-sg"
SERVICE_NAME="heliox"

echo "=== Step 6: Creating VPC Connector for App Runner ==="

# Load previous state
source /tmp/heliox_env 2>/dev/null || true

# ── Security group for VPC connector ─────────────────────────────────────────
CONNECTOR_SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null)

if [[ "$CONNECTOR_SG_ID" == "None" || -z "$CONNECTOR_SG_ID" ]]; then
  echo "Creating VPC connector security group..."
  CONNECTOR_SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$SG_NAME" \
    --description "Heliox App Runner VPC Connector — outbound to RDS and Redis" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text)

  # Outbound to RDS (5432)
  aws ec2 authorize-security-group-egress \
    --region "$REGION" \
    --group-id "$CONNECTOR_SG_ID" \
    --protocol tcp \
    --port 5432 \
    --cidr "172.31.0.0/16" > /dev/null

  # Outbound to Redis (6379)
  aws ec2 authorize-security-group-egress \
    --region "$REGION" \
    --group-id "$CONNECTOR_SG_ID" \
    --protocol tcp \
    --port 6379 \
    --cidr "172.31.0.0/16" > /dev/null

  # Outbound HTTPS (443) for AWS services (SSM, ECR, etc.)
  aws ec2 authorize-security-group-egress \
    --region "$REGION" \
    --group-id "$CONNECTOR_SG_ID" \
    --protocol tcp \
    --port 443 \
    --cidr "0.0.0.0/0" > /dev/null

  echo "  VPC connector SG: $CONNECTOR_SG_ID"
else
  echo "  VPC connector SG already exists: $CONNECTOR_SG_ID"
fi

echo "VPC_CONNECTOR_SG_ID=$CONNECTOR_SG_ID" >> /tmp/heliox_env

# ── Update RDS security group to allow inbound from VPC connector ─────────────
RDS_SG_ID="${RDS_SG_ID:-$(cat /tmp/heliox_rds_sg_id 2>/dev/null || echo "")}"

if [[ -n "$RDS_SG_ID" && "$RDS_SG_ID" != "None" ]]; then
  echo "Allowing VPC connector → RDS (5432)..."
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$RDS_SG_ID" \
    --protocol tcp \
    --port 5432 \
    --source-group "$CONNECTOR_SG_ID" 2>/dev/null \
    && echo "  Rule added." \
    || echo "  Rule already exists — skipping."
else
  echo "  WARNING: RDS_SG_ID not found. Manually allow $CONNECTOR_SG_ID → RDS SG on port 5432."
fi

# ── Update Redis security group to allow inbound from VPC connector ───────────
REDIS_SG_ID="${REDIS_SG_ID:-$(cat /tmp/heliox_redis_sg_id 2>/dev/null || echo "")}"

if [[ -n "$REDIS_SG_ID" && "$REDIS_SG_ID" != "None" ]]; then
  echo "Allowing VPC connector → Redis (6379)..."
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$REDIS_SG_ID" \
    --protocol tcp \
    --port 6379 \
    --source-group "$CONNECTOR_SG_ID" 2>/dev/null \
    && echo "  Rule added." \
    || echo "  Rule already exists — skipping."
else
  echo "  WARNING: REDIS_SG_ID not found. Manually allow $CONNECTOR_SG_ID → Redis SG on port 6379."
fi

# ── Create App Runner VPC Connector ──────────────────────────────────────────
EXISTING_CONNECTOR=$(aws apprunner list-vpc-connectors \
  --region "$REGION" \
  --query "VpcConnectors[?VpcConnectorName=='${CONNECTOR_NAME}' && Status=='ACTIVE'].VpcConnectorArn" \
  --output text 2>/dev/null)

if [[ -n "$EXISTING_CONNECTOR" && "$EXISTING_CONNECTOR" != "None" ]]; then
  echo "  VPC connector already exists: $EXISTING_CONNECTOR"
  CONNECTOR_ARN="$EXISTING_CONNECTOR"
else
  echo "Creating App Runner VPC connector..."
  CONNECTOR_ARN=$(aws apprunner create-vpc-connector \
    --region "$REGION" \
    --vpc-connector-name "$CONNECTOR_NAME" \
    --subnets \
      "subnet-0d132a65284861998" \
      "subnet-0b174fff478c3e97b" \
      "subnet-050cbfac233fcb727" \
    --security-groups "$CONNECTOR_SG_ID" \
    --query 'VpcConnector.VpcConnectorArn' \
    --output text)

  echo "  VPC connector ARN: $CONNECTOR_ARN"
fi

echo "VPC_CONNECTOR_ARN=$CONNECTOR_ARN" >> /tmp/heliox_env

# ── Update App Runner service to use VPC connector ────────────────────────────
SERVICE_ARN="${APP_RUNNER_ARN:-}"

if [[ -z "$SERVICE_ARN" ]]; then
  SERVICE_ARN=$(aws apprunner list-services \
    --region "$REGION" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn" \
    --output text 2>/dev/null)
fi

if [[ -n "$SERVICE_ARN" && "$SERVICE_ARN" != "None" ]]; then
  echo "Updating App Runner service with VPC connector..."
  aws apprunner update-service \
    --service-arn "$SERVICE_ARN" \
    --region "$REGION" \
    --network-configuration "{
      \"EgressConfiguration\": {
        \"EgressType\": \"VPC\",
        \"VpcConnectorArn\": \"${CONNECTOR_ARN}\"
      }
    }" > /dev/null

  echo "  Waiting for service update to complete..."
  while true; do
    STATUS=$(aws apprunner describe-service \
      --service-arn "$SERVICE_ARN" \
      --region "$REGION" \
      --query 'Service.Status' \
      --output text)
    echo "  Status: $STATUS"
    [[ "$STATUS" == "RUNNING" ]] && break
    [[ "$STATUS" == *"FAILED"* ]] && { echo "ERROR: Service update failed"; exit 1; }
    sleep 10
  done
  echo "  Service updated with VPC connector."
else
  echo "  NOTE: App Runner service not found yet. VPC connector ARN saved."
  echo "  Run 04_create_apprunner.sh next — it will use the VPC connector."
fi

echo ""
echo "=== Step 6 complete: VPC Connector ==="
echo "  Connector ARN : $CONNECTOR_ARN"
echo "  Connector SG  : $CONNECTOR_SG_ID"
echo "  App Runner can now reach RDS and Redis within the VPC."
