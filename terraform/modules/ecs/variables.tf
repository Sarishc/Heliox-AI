variable "environment" {
  description = "Environment name"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "List of private subnet IDs"
  type        = list(string)
}

variable "alb_target_group_arn" {
  description = "ARN of ALB target group"
  type        = string
}

variable "alb_security_group_id" {
  description = "ID of ALB security group"
  type        = string
}

variable "api_image" {
  description = "Docker image for API service"
  type        = string
}

variable "worker_image" {
  description = "Docker image for worker service"
  type        = string
}

variable "api_cpu" {
  description = "CPU units for API service"
  type        = number
}

variable "api_memory" {
  description = "Memory for API service in MB"
  type        = number
}

variable "worker_cpu" {
  description = "CPU units for worker service"
  type        = number
}

variable "worker_memory" {
  description = "Memory for worker service in MB"
  type        = number
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
}

variable "worker_desired_count" {
  description = "Desired number of worker tasks"
  type        = number
}

variable "database_url" {
  description = "Database connection URL"
  type        = string
  sensitive   = true
}

variable "redis_url" {
  description = "Redis connection URL"
  type        = string
  sensitive   = true
}

variable "frontend_url" {
  description = "Frontend URL"
  type        = string
}

variable "secret_key_arn" {
  description = "ARN of SSM parameter for SECRET_KEY"
  type        = string
}

variable "admin_api_key_arn" {
  description = "ARN of SSM parameter for ADMIN_API_KEY"
  type        = string
}

variable "integrations_encryption_key_arn" {
  description = "ARN of SSM parameter for INTEGRATIONS_ENCRYPTION_KEY"
  type        = string
}

variable "stripe_secret_key_arn" {
  description = "ARN of SSM parameter for STRIPE_SECRET_KEY"
  type        = string
  default     = ""
}

variable "stripe_webhook_secret_arn" {
  description = "ARN of SSM parameter for STRIPE_WEBHOOK_SECRET"
  type        = string
  default     = ""
}

variable "google_client_id_arn" {
  description = "ARN of SSM parameter for GOOGLE_CLIENT_ID"
  type        = string
  default     = ""
}

variable "google_client_secret_arn" {
  description = "ARN of SSM parameter for GOOGLE_CLIENT_SECRET"
  type        = string
  default     = ""
}

variable "log_group_name" {
  description = "CloudWatch log group name"
  type        = string
}

variable "log_group_arn" {
  description = "CloudWatch log group ARN"
  type        = string
  default     = ""
}

variable "s3_bucket_name" {
  description = "S3 bucket name"
  type        = string
}

variable "alb_arn_suffix" {
  description = "ALB ARN suffix for 5xx alarm (app/name/id)"
  type        = string
  default     = ""
}

variable "alarm_sns_topic_arn" {
  description = "SNS topic ARN for alarm notifications"
  type        = string
  default     = ""
}

variable "elasticache_security_group_id" {
  description = "ID of the ElastiCache security group (for explicit port 6379 egress rule)"
  type        = string
}
