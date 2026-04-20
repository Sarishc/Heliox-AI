/**
 * Heliox Infrastructure on AWS
 * 
 * This Terraform configuration deploys the complete Heliox stack on AWS:
 * - VPC with public/private subnets
 * - RDS Postgres database
 * - ElastiCache Redis cluster
 * - ECS Fargate services (API, worker, beat)
 * - Application Load Balancer with HTTPS
 * - S3 bucket for artifacts
 * - CloudWatch logs
 */

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Uncomment to use remote state
  # backend "s3" {
  #   bucket         = "your-terraform-state-bucket"
  #   key            = "heliox/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "terraform-state-lock"
  # }
}

provider "aws" {
  region = var.aws_region
  
  default_tags {
    tags = {
      Project     = "Heliox"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# VPC Module
module "vpc" {
  source = "./modules/vpc"
  
  environment         = var.environment
  vpc_cidr            = var.vpc_cidr
  availability_zones  = data.aws_availability_zones.available.names
  public_subnet_cidrs = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
}

# RDS Module
module "rds" {
  source = "./modules/rds"
  
  environment           = var.environment
  vpc_id                = module.vpc.vpc_id
  private_subnet_ids    = module.vpc.private_subnet_ids
  db_name               = var.db_name
  db_username           = var.db_username
  db_password           = var.db_password
  db_instance_class     = var.db_instance_class
  db_allocated_storage  = var.db_allocated_storage
  backup_retention_days = var.backup_retention_days
  allowed_security_groups = [module.ecs.ecs_security_group_id]
}

# Redis Module
module "redis" {
  source = "./modules/redis"
  
  environment             = var.environment
  vpc_id                  = module.vpc.vpc_id
  private_subnet_ids      = module.vpc.private_subnet_ids
  node_type               = var.redis_node_type
  num_cache_nodes         = var.redis_num_nodes
  allowed_security_groups = [module.ecs.ecs_security_group_id]
}

# S3 Bucket Module
module "s3" {
  source = "./modules/s3"
  
  environment = var.environment
  bucket_name = var.s3_bucket_name
}

# CloudWatch Module (logs, dashboard)
module "cloudwatch" {
  source = "./modules/cloudwatch"

  environment       = var.environment
  retention_in_days = var.log_retention_days
}

# Application Load Balancer Module
module "alb" {
  source = "./modules/alb"
  
  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  public_subnet_ids  = module.vpc.public_subnet_ids
  certificate_arn    = var.acm_certificate_arn
  domain_name        = var.domain_name
  health_check_path  = "/api/v1/health"
}

# ECS Cluster and Services Module
module "ecs" {
  source = "./modules/ecs"
  
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnet_ids
  alb_target_group_arn   = module.alb.target_group_arn
  alb_security_group_id  = module.alb.alb_security_group_id
  
  # Container configuration
  api_image              = var.api_image
  worker_image           = var.worker_image
  api_cpu                = var.api_cpu
  api_memory             = var.api_memory
  worker_cpu             = var.worker_cpu
  worker_memory          = var.worker_memory
  api_desired_count      = var.api_desired_count
  worker_desired_count   = var.worker_desired_count
  
  # Environment variables
  database_url           = module.rds.database_url
  redis_url              = module.redis.redis_url
  frontend_url           = "https://${var.domain_name}"
  
  # Secrets from SSM Parameter Store
  secret_key_arn             = var.secret_key_ssm_arn
  admin_api_key_arn          = var.admin_api_key_ssm_arn
  integrations_encryption_key_arn = var.integrations_encryption_key_ssm_arn
  stripe_secret_key_arn      = var.stripe_secret_key_ssm_arn
  stripe_webhook_secret_arn  = var.stripe_webhook_secret_ssm_arn
  google_client_id_arn       = var.google_client_id_ssm_arn
  google_client_secret_arn   = var.google_client_secret_ssm_arn
  
  # Logging
  log_group_name         = module.cloudwatch.log_group_name
  log_group_arn          = module.cloudwatch.log_group_arn

  # S3 bucket
  s3_bucket_name         = module.s3.bucket_name

  # CloudWatch alarms
  alb_arn_suffix         = module.alb.alb_arn_suffix
  alarm_sns_topic_arn    = var.alarm_sns_topic_arn

  # Security: explicit ECS → ElastiCache egress rule on port 6379
  elasticache_security_group_id = module.redis.security_group_id
}

# Outputs
output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.alb.alb_dns_name
}

output "alb_url" {
  description = "URL of the Application Load Balancer"
  value       = "https://${var.domain_name}"
}

output "database_endpoint" {
  description = "RDS database endpoint"
  value       = module.rds.db_endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "Redis cluster endpoint"
  value       = module.redis.redis_endpoint
  sensitive   = true
}

output "s3_bucket_name" {
  description = "S3 bucket name for artifacts"
  value       = module.s3.bucket_name
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.ecs.cluster_name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = module.cloudwatch.log_group_name
}
