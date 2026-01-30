output "cluster_id" {
  description = "ID of the ECS cluster"
  value       = aws_ecs_cluster.main.id
}

output "cluster_arn" {
  description = "ARN of the ECS cluster"
  value       = aws_ecs_cluster.main.arn
}

output "cluster_name" {
  description = "Name of the ECS cluster"
  value       = aws_ecs_cluster.main.name
}

output "api_service_id" {
  description = "ID of the API service"
  value       = aws_ecs_service.api.id
}

output "api_service_name" {
  description = "Name of the API service"
  value       = aws_ecs_service.api.name
}

output "worker_service_id" {
  description = "ID of the worker service"
  value       = aws_ecs_service.worker.id
}

output "worker_service_name" {
  description = "Name of the worker service"
  value       = aws_ecs_service.worker.name
}

output "beat_service_id" {
  description = "ID of the beat service"
  value       = aws_ecs_service.beat.id
}

output "beat_service_name" {
  description = "Name of the beat service"
  value       = aws_ecs_service.beat.name
}

output "ecs_security_group_id" {
  description = "ID of the ECS tasks security group"
  value       = aws_security_group.ecs_tasks.id
}

output "ecs_execution_role_arn" {
  description = "ARN of the ECS execution role"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role"
  value       = aws_iam_role.ecs_task.arn
}
