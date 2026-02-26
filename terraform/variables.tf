/**
 * Terraform Variables for Heliox Deployment
 */

# General Configuration
variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, production)"
  type        = string
  default     = "production"
}

variable "domain_name" {
  description = "Domain name for the application (e.g., heliox.company.com)"
  type        = string
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

# RDS Configuration
variable "db_name" {
  description = "Database name"
  type        = string
  default     = "heliox"
}

variable "db_username" {
  description = "Database master username"
  type        = string
  default     = "heliox_admin"
}

variable "db_password" {
  description = "Database master password"
  type        = string
  sensitive   = true
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "db_allocated_storage" {
  description = "Allocated storage for RDS in GB"
  type        = number
  default     = 100
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 7
}

# Redis Configuration
variable "redis_node_type" {
  description = "ElastiCache Redis node type"
  type        = string
  default     = "cache.t3.medium"
}

variable "redis_num_nodes" {
  description = "Number of Redis cache nodes"
  type        = number
  default     = 1
}

# ECS Configuration
variable "api_image" {
  description = "Docker image for API service"
  type        = string
  default     = "heliox/api:latest"
}

variable "worker_image" {
  description = "Docker image for worker service"
  type        = string
  default     = "heliox/worker:latest"
}

variable "api_cpu" {
  description = "CPU units for API service (1024 = 1 vCPU)"
  type        = number
  default     = 1024
}

variable "api_memory" {
  description = "Memory for API service in MB"
  type        = number
  default     = 2048
}

variable "worker_cpu" {
  description = "CPU units for worker service"
  type        = number
  default     = 512
}

variable "worker_memory" {
  description = "Memory for worker service in MB"
  type        = number
  default     = 1024
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of worker tasks"
  type        = number
  default     = 1
}

# S3 Configuration
variable "s3_bucket_name" {
  description = "S3 bucket name for artifacts (must be globally unique)"
  type        = string
}

# CloudWatch Configuration
variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for CloudWatch alarm notifications (optional)"
  type        = string
  default     = ""
}

# SSL Certificate
variable "acm_certificate_arn" {
  description = "ARN of ACM certificate for HTTPS"
  type        = string
}

# Secrets (SSM Parameter Store ARNs)
variable "secret_key_ssm_arn" {
  description = "ARN of SSM parameter for SECRET_KEY"
  type        = string
}

variable "admin_api_key_ssm_arn" {
  description = "ARN of SSM parameter for ADMIN_API_KEY"
  type        = string
}

variable "integrations_encryption_key_ssm_arn" {
  description = "ARN of SSM parameter for INTEGRATIONS_ENCRYPTION_KEY"
  type        = string
}

variable "stripe_secret_key_ssm_arn" {
  description = "ARN of SSM parameter for STRIPE_SECRET_KEY"
  type        = string
  default     = ""
}

variable "stripe_webhook_secret_ssm_arn" {
  description = "ARN of SSM parameter for STRIPE_WEBHOOK_SECRET"
  type        = string
  default     = ""
}

variable "google_client_id_ssm_arn" {
  description = "ARN of SSM parameter for GOOGLE_CLIENT_ID"
  type        = string
  default     = ""
}

variable "google_client_secret_ssm_arn" {
  description = "ARN of SSM parameter for GOOGLE_CLIENT_SECRET"
  type        = string
  default     = ""
}
