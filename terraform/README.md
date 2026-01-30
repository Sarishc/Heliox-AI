# Heliox AWS Infrastructure with Terraform

This directory contains Terraform configurations to deploy Heliox on AWS using best practices for production workloads.

## Architecture Overview

The infrastructure includes:
- **VPC** with public and private subnets across 2 availability zones
- **RDS Postgres** (Multi-AZ for production) for application database
- **ElastiCache Redis** for caching and Celery message broker
- **ECS Fargate** services for API, Worker, and Beat (scheduler)
- **Application Load Balancer** with HTTPS and automatic HTTP→HTTPS redirect
- **S3 bucket** for artifacts with encryption and lifecycle policies
- **CloudWatch** logs and monitoring dashboard
- **IAM roles** with least-privilege access
- **Auto-scaling** for API service based on CPU utilization

```
┌─────────────────────────────────────────────────────────────┐
│                         Internet                            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Application Load    │
              │  Balancer (HTTPS)    │
              └──────────┬───────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐      ┌────────┐      ┌────────┐
    │  API   │      │ Worker │      │  Beat  │
    │ (ECS)  │      │ (ECS)  │      │ (ECS)  │
    └────┬───┘      └────┬───┘      └────┬───┘
         │               │               │
         └───────────────┼───────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
    ┌────────┐      ┌────────┐      ┌────────┐
    │  RDS   │      │ Redis  │      │   S3   │
    │Postgres│      │ElastiCache│   │ Bucket │
    └────────┘      └────────┘      └────────┘
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **Terraform** >= 1.0 installed
4. **Domain name** with DNS access
5. **SSL Certificate** in AWS Certificate Manager (ACM)
6. **Docker images** pushed to ECR

### Install Prerequisites

```bash
# Install Terraform (macOS)
brew install terraform

# Install AWS CLI (macOS)
brew install awscli

# Configure AWS CLI
aws configure
```

## Step-by-Step Deployment

### Step 1: Prepare AWS Account

#### 1.1 Create ACM Certificate

```bash
# Request certificate for your domain
aws acm request-certificate \
  --domain-name heliox.company.com \
  --validation-method DNS \
  --region us-east-1

# Note the CertificateArn from output
# Validate certificate via DNS (add CNAME records to your DNS)
```

#### 1.2 Create ECR Repositories

```bash
# Create repositories for Docker images
aws ecr create-repository --repository-name heliox/api --region us-east-1
aws ecr create-repository --repository-name heliox/worker --region us-east-1

# Note the repository URIs
```

#### 1.3 Build and Push Docker Images

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com

# Build API image
cd backend
docker build -t heliox/api:latest .
docker tag heliox/api:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/api:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/api:latest

# Build Worker image (same Dockerfile, different command)
docker tag heliox/api:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/worker:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/worker:latest
```

### Step 2: Create Secrets in SSM Parameter Store

All sensitive configuration values should be stored in AWS Systems Manager Parameter Store as SecureString parameters.

```bash
# Generate secrets (use strong values!)
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
ADMIN_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
INTEGRATIONS_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")

# Create required parameters
aws ssm put-parameter \
  --name "/heliox/production/SECRET_KEY" \
  --value "$SECRET_KEY" \
  --type SecureString \
  --region us-east-1

aws ssm put-parameter \
  --name "/heliox/production/ADMIN_API_KEY" \
  --value "$ADMIN_API_KEY" \
  --type SecureString \
  --region us-east-1

aws ssm put-parameter \
  --name "/heliox/production/INTEGRATIONS_ENCRYPTION_KEY" \
  --value "$INTEGRATIONS_KEY" \
  --type SecureString \
  --region us-east-1

# Optional: Stripe (if using billing features)
aws ssm put-parameter \
  --name "/heliox/production/STRIPE_SECRET_KEY" \
  --value "sk_live_..." \
  --type SecureString \
  --region us-east-1

aws ssm put-parameter \
  --name "/heliox/production/STRIPE_WEBHOOK_SECRET" \
  --value "whsec_..." \
  --type SecureString \
  --region us-east-1

# Optional: Google OAuth (if using SSO)
aws ssm put-parameter \
  --name "/heliox/production/GOOGLE_CLIENT_ID" \
  --value "your-client-id.apps.googleusercontent.com" \
  --type SecureString \
  --region us-east-1

aws ssm put-parameter \
  --name "/heliox/production/GOOGLE_CLIENT_SECRET" \
  --value "GOCSPX-..." \
  --type SecureString \
  --region us-east-1

# Get ARNs for terraform.tfvars
aws ssm get-parameter --name "/heliox/production/SECRET_KEY" --query 'Parameter.ARN' --output text
```

### Step 3: Configure Terraform Variables

```bash
# Copy example tfvars file
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values
nano terraform.tfvars
```

Update the following in `terraform.tfvars`:

```hcl
# Required values:
domain_name         = "heliox.company.com"
acm_certificate_arn = "arn:aws:acm:us-east-1:123456789012:certificate/..."
db_password         = "STRONG_PASSWORD_HERE"
api_image           = "123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/api:latest"
worker_image        = "123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/worker:latest"
s3_bucket_name      = "heliox-artifacts-prod-123456"  # Must be globally unique

# SSM Parameter ARNs (from Step 2)
secret_key_ssm_arn                  = "arn:aws:ssm:us-east-1:123456789012:parameter/heliox/production/SECRET_KEY"
admin_api_key_ssm_arn               = "arn:aws:ssm:us-east-1:123456789012:parameter/heliox/production/ADMIN_API_KEY"
integrations_encryption_key_ssm_arn = "arn:aws:ssm:us-east-1:123456789012:parameter/heliox/production/INTEGRATIONS_ENCRYPTION_KEY"
```

### Step 4: Deploy Infrastructure

```bash
# Navigate to terraform directory
cd terraform

# Initialize Terraform
terraform init

# Review planned changes
terraform plan

# Apply configuration (this will take 15-20 minutes)
terraform apply

# Note the outputs (ALB DNS name, service names, etc.)
```

### Step 5: Configure DNS

Point your domain to the ALB:

```bash
# Get ALB DNS name from terraform output
ALB_DNS=$(terraform output -raw alb_dns_name)

# Create CNAME record in your DNS provider:
# heliox.company.com -> <alb_dns_name>
```

Example for Route 53:

```bash
# Get ALB hosted zone ID
ALB_ZONE_ID=$(terraform output -raw alb_zone_id)

# Create alias record
aws route53 change-resource-record-sets \
  --hosted-zone-id YOUR_HOSTED_ZONE_ID \
  --change-batch '{
    "Changes": [{
      "Action": "CREATE",
      "ResourceRecordSet": {
        "Name": "heliox.company.com",
        "Type": "A",
        "AliasTarget": {
          "HostedZoneId": "'$ALB_ZONE_ID'",
          "DNSName": "'$ALB_DNS'",
          "EvaluateTargetHealth": true
        }
      }
    }]
  }'
```

### Step 6: Run Database Migrations

```bash
# Get ECS cluster and task details
CLUSTER_NAME=$(terraform output -raw ecs_cluster_name)
API_SERVICE=$(terraform output -raw api_service_name)

# List running tasks
TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER_NAME \
  --service-name $API_SERVICE \
  --query 'taskArns[0]' \
  --output text)

# Run migrations using ECS Exec
aws ecs execute-command \
  --cluster $CLUSTER_NAME \
  --task $(basename $TASK_ARN) \
  --container api \
  --command "alembic upgrade head" \
  --interactive
```

Alternative: Run migrations from local machine:

```bash
# Get database endpoint
DB_ENDPOINT=$(terraform output -raw database_endpoint)
DB_PASSWORD="your-db-password"

# Export connection string
export DATABASE_URL="postgresql://heliox_admin:$DB_PASSWORD@$DB_ENDPOINT/heliox"

# Run migrations
cd backend
alembic upgrade head
```

### Step 7: Verify Deployment

```bash
# Check services are running
aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services $API_SERVICE \
  --query 'services[0].{desired:desiredCount,running:runningCount,status:status}'

# View logs
aws logs tail /ecs/heliox-production --follow

# Test API endpoint
curl https://heliox.company.com/health
```

### Step 8: Initial Setup

Access the application and create admin user:

```bash
# Option 1: Use admin API key directly
ADMIN_KEY=$(aws ssm get-parameter \
  --name "/heliox/production/ADMIN_API_KEY" \
  --with-decryption \
  --query 'Parameter.Value' \
  --output text)

curl -X POST https://heliox.company.com/api/v1/admin/onboard \
  -H "X-API-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "org_name": "My Company",
    "admin_email": "admin@company.com",
    "admin_password": "secure_password_here"
  }'

# Option 2: Seed demo data (development only)
curl -X POST https://heliox.company.com/api/v1/admin/demo/seed \
  -H "X-API-Key: $ADMIN_KEY"
```

## Cost Estimation

Approximate monthly costs for production deployment:

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| ECS Fargate (API 2x) | 2 vCPU, 4 GB RAM | ~$70 |
| ECS Fargate (Worker 1x) | 0.5 vCPU, 1 GB RAM | ~$18 |
| ECS Fargate (Beat 1x) | 0.25 vCPU, 0.5 GB RAM | ~$9 |
| RDS Postgres (Multi-AZ) | db.t3.medium | ~$120 |
| ElastiCache Redis | cache.t3.medium | ~$50 |
| ALB | Standard pricing | ~$25 |
| NAT Gateway (2x AZ) | Data transfer | ~$90 |
| S3 | 100 GB storage | ~$3 |
| CloudWatch Logs | 10 GB/month | ~$5 |
| **Total** | | **~$390/month** |

To reduce costs:
- Use single AZ for non-production (saves ~$120/month)
- Use smaller instance sizes for dev/staging
- Reduce API task count to 1 for dev (saves ~$35/month)
- Use RDS t3.micro for dev (saves ~$100/month)

## Maintenance

### Update Application

```bash
# Build and push new image
docker build -t heliox/api:v1.1.0 backend/
docker tag heliox/api:v1.1.0 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/api:v1.1.0
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/heliox/api:v1.1.0

# Update terraform.tfvars with new image tag
# terraform apply

# Or force new deployment without changing image
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $API_SERVICE \
  --force-new-deployment
```

### Scale Services

```bash
# Temporarily increase API capacity
aws ecs update-service \
  --cluster $CLUSTER_NAME \
  --service $API_SERVICE \
  --desired-count 4

# Or update terraform.tfvars and apply:
# api_desired_count = 4
# terraform apply
```

### View Logs

```bash
# Tail all logs
aws logs tail /ecs/heliox-production --follow

# Filter by service
aws logs tail /ecs/heliox-production --follow --filter-pattern "api"

# View specific time range
aws logs tail /ecs/heliox-production --since 1h
```

### Backup Database

RDS automated backups are enabled by default (7-day retention). Manual snapshot:

```bash
aws rds create-db-snapshot \
  --db-instance-identifier heliox-production-db \
  --db-snapshot-identifier heliox-manual-snapshot-$(date +%Y%m%d)
```

### Monitor Resources

```bash
# Open CloudWatch dashboard
aws cloudwatch get-dashboard \
  --dashboard-name heliox-production

# View ECS service metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/ECS \
  --metric-name CPUUtilization \
  --dimensions Name=ServiceName,Value=$API_SERVICE \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average
```

## Troubleshooting

### Services Not Starting

```bash
# Check service events
aws ecs describe-services \
  --cluster $CLUSTER_NAME \
  --services $API_SERVICE \
  --query 'services[0].events[0:5]'

# Check task logs
aws logs tail /ecs/heliox-production --since 30m
```

### Database Connection Issues

```bash
# Verify security groups allow ECS→RDS traffic
aws ec2 describe-security-groups \
  --group-ids $(terraform output -raw rds_security_group_id)

# Test connection from ECS task
aws ecs execute-command \
  --cluster $CLUSTER_NAME \
  --task $TASK_ARN \
  --container api \
  --command "pg_isready -h $DB_ENDPOINT -U heliox_admin" \
  --interactive
```

### High Costs

```bash
# Identify most expensive resources
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --group-by Type=SERVICE

# Check NAT Gateway data transfer
aws cloudwatch get-metric-statistics \
  --namespace AWS/NATGateway \
  --metric-name BytesOutToDestination \
  --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

## Cleanup

To destroy all resources:

```bash
# WARNING: This will delete everything!
terraform destroy

# Manually delete SSM parameters if needed
aws ssm delete-parameter --name "/heliox/production/SECRET_KEY"
aws ssm delete-parameter --name "/heliox/production/ADMIN_API_KEY"
# ... delete other parameters
```

## Security Best Practices

1. ✅ **Secrets Management**: All secrets stored in SSM Parameter Store (encrypted)
2. ✅ **Network Security**: Private subnets for ECS/RDS/Redis
3. ✅ **Encryption**: RDS and Redis encryption at rest enabled
4. ✅ **HTTPS Only**: ALB redirects HTTP to HTTPS
5. ✅ **Least Privilege**: IAM roles follow principle of least privilege
6. ✅ **Multi-AZ**: RDS Multi-AZ for production high availability
7. ✅ **Backups**: Automated RDS backups with 7-day retention
8. ✅ **Monitoring**: CloudWatch logs and Container Insights enabled
9. ✅ **Security Groups**: Restrictive inbound/outbound rules

## Support

For issues or questions:
- Review CloudWatch logs: `/ecs/heliox-production`
- Check ECS service events
- Verify environment variables and secrets
- Review this README and terraform documentation

## License

Terraform configurations for Heliox infrastructure.
