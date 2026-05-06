#!/bin/bash
set -euo pipefail
# Creates ElastiCache Redis 7 cluster for Heliox.
# cache.t3.micro — single node, cheapest option.

REGION="us-east-1"
VPC_ID="vpc-0fe7c9eb87a51bc0e"
CLUSTER_ID="heliox-redis"
SG_NAME="heliox-redis-sg"
SUBNET_GROUP_NAME="heliox-redis-subnet-group"

echo "=== Step 2: Creating ElastiCache Redis ==="

# ── Security group for Redis ──────────────────────────────────────────────────
SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null)

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
  echo "Creating Redis security group..."
  SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$SG_NAME" \
    --description "Heliox ElastiCache Redis — allows port 6379 from App Runner VPC connector" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text)

  # Allow Redis from within the VPC
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port 6379 \
    --cidr "172.31.0.0/16" > /dev/null

  echo "  Redis security group: $SG_ID"
else
  echo "  Redis security group already exists: $SG_ID"
fi

echo "$SG_ID" > /tmp/heliox_redis_sg_id
echo "REDIS_SG_ID=$SG_ID" >> /tmp/heliox_env

# ── ElastiCache subnet group ──────────────────────────────────────────────────
if aws elasticache describe-cache-subnet-groups \
    --cache-subnet-group-name "$SUBNET_GROUP_NAME" \
    --region "$REGION" &>/dev/null; then
  echo "  Cache subnet group already exists — skipping"
else
  echo "Creating ElastiCache subnet group..."
  aws elasticache create-cache-subnet-group \
    --region "$REGION" \
    --cache-subnet-group-name "$SUBNET_GROUP_NAME" \
    --cache-subnet-group-description "Heliox Redis subnet group" \
    --subnet-ids \
      "subnet-0d132a65284861998" \
      "subnet-0b174fff478c3e97b" \
      "subnet-050cbfac233fcb727" > /dev/null
  echo "  Cache subnet group created."
fi

# ── Create ElastiCache Redis cluster ─────────────────────────────────────────
if aws elasticache describe-cache-clusters \
    --cache-cluster-id "$CLUSTER_ID" \
    --region "$REGION" &>/dev/null; then
  echo "  Redis cluster $CLUSTER_ID already exists — fetching endpoint..."
else
  echo "Creating ElastiCache Redis cluster (cache.t3.micro, Redis 7)..."
  echo "  This takes ~5-8 minutes..."

  aws elasticache create-cache-cluster \
    --region "$REGION" \
    --cache-cluster-id "$CLUSTER_ID" \
    --cache-node-type cache.t3.micro \
    --engine redis \
    --engine-version "7.0" \
    --num-cache-nodes 1 \
    --cache-subnet-group-name "$SUBNET_GROUP_NAME" \
    --security-group-ids "$SG_ID" \
    --tags "Key=Project,Value=Heliox" "Key=Environment,Value=production" > /dev/null

  echo "  Waiting for Redis cluster to become available..."
  aws elasticache wait cache-cluster-available \
    --cache-cluster-id "$CLUSTER_ID" \
    --region "$REGION"
fi

# ── Get endpoint ──────────────────────────────────────────────────────────────
REDIS_ENDPOINT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id "$CLUSTER_ID" \
  --region "$REGION" \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' \
  --output text)

REDIS_PORT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id "$CLUSTER_ID" \
  --region "$REGION" \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Port' \
  --output text)

REDIS_URL="redis://${REDIS_ENDPOINT}:${REDIS_PORT}/0"

echo "$REDIS_ENDPOINT" > /tmp/heliox_redis_endpoint
echo "REDIS_ENDPOINT=$REDIS_ENDPOINT" >> /tmp/heliox_env
echo "REDIS_URL=$REDIS_URL" >> /tmp/heliox_env

echo ""
echo "=== Step 2 complete: ElastiCache Redis ==="
echo "  Endpoint : $REDIS_ENDPOINT:$REDIS_PORT"
echo "  URL      : $REDIS_URL"
echo "  SG ID    : $SG_ID"
