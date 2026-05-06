#!/bin/bash
set -euo pipefail
# Creates RDS PostgreSQL 15 instance for Heliox.
# Free tier eligible: db.t3.micro, 20GB gp2.

REGION="us-east-1"
VPC_ID="vpc-0fe7c9eb87a51bc0e"
DB_INSTANCE_ID="heliox-db"
DB_NAME="heliox"
DB_USERNAME="heliox"
SUBNET_GROUP_NAME="heliox-db-subnet-group"
SG_NAME="heliox-rds-sg"

echo "=== Step 1: Creating RDS PostgreSQL ==="

# ── Security group for RDS ────────────────────────────────────────────────────
SG_ID=$(aws ec2 describe-security-groups \
  --region "$REGION" \
  --filters "Name=group-name,Values=${SG_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null)

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
  echo "Creating RDS security group..."
  SG_ID=$(aws ec2 create-security-group \
    --region "$REGION" \
    --group-name "$SG_NAME" \
    --description "Heliox RDS PostgreSQL — allows port 5432 from App Runner VPC connector" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text)

  # Allow PostgreSQL from within the VPC (App Runner VPC connector will be in the same VPC)
  aws ec2 authorize-security-group-ingress \
    --region "$REGION" \
    --group-id "$SG_ID" \
    --protocol tcp \
    --port 5432 \
    --cidr "172.31.0.0/16" > /dev/null

  echo "  RDS security group: $SG_ID"
else
  echo "  RDS security group already exists: $SG_ID"
fi

# Save for later scripts
echo "$SG_ID" > /tmp/heliox_rds_sg_id
echo "RDS_SG_ID=$SG_ID" >> /tmp/heliox_env

# ── DB subnet group (needs 2+ AZs for RDS) ───────────────────────────────────
if aws rds describe-db-subnet-groups \
    --db-subnet-group-name "$SUBNET_GROUP_NAME" \
    --region "$REGION" &>/dev/null; then
  echo "  DB subnet group already exists — skipping"
else
  echo "Creating DB subnet group..."
  aws rds create-db-subnet-group \
    --region "$REGION" \
    --db-subnet-group-name "$SUBNET_GROUP_NAME" \
    --db-subnet-group-description "Heliox RDS subnet group" \
    --subnet-ids \
      "subnet-0d132a65284861998" \
      "subnet-0b174fff478c3e97b" \
      "subnet-050cbfac233fcb727" > /dev/null
  echo "  DB subnet group created."
fi

# ── Generate and store DB password ───────────────────────────────────────────
echo "Generating DB password..."
DB_PASSWORD=$(openssl rand -hex 24)

aws ssm put-parameter \
  --region "$REGION" \
  --name "/heliox/DB_PASSWORD" \
  --value "$DB_PASSWORD" \
  --type SecureString \
  --overwrite > /dev/null

echo "  DB password saved to SSM: /heliox/DB_PASSWORD"

# ── Create RDS instance ───────────────────────────────────────────────────────
if aws rds describe-db-instances \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --region "$REGION" &>/dev/null; then
  echo "  RDS instance $DB_INSTANCE_ID already exists — fetching endpoint..."
else
  echo "Creating RDS PostgreSQL 15 instance (db.t3.micro, 20GB)..."
  echo "  This takes ~5-10 minutes..."

  aws rds create-db-instance \
    --region "$REGION" \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --db-instance-class db.t3.micro \
    --engine postgres \
    --engine-version "15" \
    --master-username "$DB_USERNAME" \
    --master-user-password "$DB_PASSWORD" \
    --db-name "$DB_NAME" \
    --allocated-storage 20 \
    --storage-type gp2 \
    --no-multi-az \
    --no-publicly-accessible \
    --backup-retention-period 7 \
    --db-subnet-group-name "$SUBNET_GROUP_NAME" \
    --vpc-security-group-ids "$SG_ID" \
    --storage-encrypted \
    --deletion-protection \
    --tags "Key=Project,Value=Heliox" "Key=Environment,Value=production" > /dev/null

  echo "  Waiting for RDS instance to become available..."
  aws rds wait db-instance-available \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --region "$REGION"
fi

# ── Get endpoint ─────────────────────────────────────────────────────────────
DB_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$DB_INSTANCE_ID" \
  --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

DATABASE_URL="postgresql+psycopg2://${DB_USERNAME}:${DB_PASSWORD}@${DB_ENDPOINT}:5432/${DB_NAME}"

# Save endpoint for subsequent scripts
echo "$DB_ENDPOINT" > /tmp/heliox_db_endpoint
echo "DB_ENDPOINT=$DB_ENDPOINT" >> /tmp/heliox_env
echo "DATABASE_URL=$DATABASE_URL" >> /tmp/heliox_env

echo ""
echo "=== Step 1 complete: RDS PostgreSQL ==="
echo "  Endpoint : $DB_ENDPOINT"
echo "  Database : $DB_NAME"
echo "  Username : $DB_USERNAME"
echo "  Password : saved to SSM /heliox/DB_PASSWORD"
echo "  SG ID    : $SG_ID"
