/**
 * Terraform Outputs for Heliox Deployment
 */

output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "public_subnet_ids" {
  description = "IDs of public subnets"
  value       = module.vpc.public_subnet_ids
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.alb.alb_dns_name
}

output "application_url" {
  description = "URL to access the Heliox application"
  value       = "https://${var.domain_name}"
}

output "database_endpoint" {
  description = "RDS Postgres endpoint"
  value       = module.rds.db_endpoint
  sensitive   = true
}

output "database_name" {
  description = "Database name"
  value       = var.db_name
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

output "s3_bucket_arn" {
  description = "S3 bucket ARN"
  value       = module.s3.bucket_arn
}

output "ecs_cluster_name" {
  description = "Name of the ECS cluster"
  value       = module.ecs.cluster_name
}

output "ecs_cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = module.ecs.cluster_arn
}

output "api_service_name" {
  description = "Name of the API ECS service"
  value       = module.ecs.api_service_name
}

output "worker_service_name" {
  description = "Name of the Worker ECS service"
  value       = module.ecs.worker_service_name
}

output "beat_service_name" {
  description = "Name of the Beat ECS service"
  value       = module.ecs.beat_service_name
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group name"
  value       = module.cloudwatch.log_group_name
}

output "deployment_instructions" {
  description = "Next steps after deployment"
  value       = <<-EOT
    Heliox has been deployed successfully!
    
    Next steps:
    1. Point your DNS (${var.domain_name}) to: ${module.alb.alb_dns_name}
    2. Access the application at: https://${var.domain_name}
    3. View logs: aws logs tail ${module.cloudwatch.log_group_name} --follow
    4. Run migrations: 
       aws ecs execute-command --cluster ${module.ecs.cluster_name} \
         --task <task-id> --container api \
         --command "alembic upgrade head" --interactive
    
    Useful commands:
    - List tasks: aws ecs list-tasks --cluster ${module.ecs.cluster_name}
    - Update service: aws ecs update-service --cluster ${module.ecs.cluster_name} \
                      --service ${module.ecs.api_service_name} --force-new-deployment
  EOT
}
