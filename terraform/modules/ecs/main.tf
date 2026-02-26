/**
 * ECS Module
 * Creates ECS cluster and Fargate services for API, Worker, and Beat
 */

# ECS Cluster
resource "aws_ecs_cluster" "main" {
  name = "heliox-${var.environment}"
  
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  
  tags = {
    Name        = "heliox-${var.environment}-cluster"
    Environment = var.environment
  }
}

# Security Group for ECS Tasks
resource "aws_security_group" "ecs_tasks" {
  name        = "heliox-${var.environment}-ecs-tasks-sg"
  description = "Security group for Heliox ECS tasks"
  vpc_id      = var.vpc_id
  
  ingress {
    description     = "HTTP from ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [var.alb_security_group_id]
  }
  
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  tags = {
    Name        = "heliox-${var.environment}-ecs-tasks-sg"
    Environment = var.environment
  }
}

# IAM Role for ECS Task Execution
resource "aws_iam_role" "ecs_execution" {
  name = "heliox-${var.environment}-ecs-execution-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name        = "heliox-${var.environment}-ecs-execution-role"
    Environment = var.environment
  }
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Additional policy for SSM Parameter Store access
resource "aws_iam_role_policy" "ecs_execution_ssm" {
  name = "heliox-${var.environment}-ecs-execution-ssm"
  role = aws_iam_role.ecs_execution.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameters",
          "ssm:GetParameter",
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          var.secret_key_arn,
          var.admin_api_key_arn,
          var.integrations_encryption_key_arn,
          var.stripe_secret_key_arn != "" ? var.stripe_secret_key_arn : "arn:aws:ssm:*:*:parameter/dummy",
          var.stripe_webhook_secret_arn != "" ? var.stripe_webhook_secret_arn : "arn:aws:ssm:*:*:parameter/dummy",
          var.google_client_id_arn != "" ? var.google_client_id_arn : "arn:aws:ssm:*:*:parameter/dummy",
          var.google_client_secret_arn != "" ? var.google_client_secret_arn : "arn:aws:ssm:*:*:parameter/dummy"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = "*"
      }
    ]
  })
}

# IAM Role for ECS Tasks (application permissions)
resource "aws_iam_role" "ecs_task" {
  name = "heliox-${var.environment}-ecs-task-role"
  
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
  
  tags = {
    Name        = "heliox-${var.environment}-ecs-task-role"
    Environment = var.environment
  }
}

# S3 access policy for task role
resource "aws_iam_role_policy" "ecs_task_s3" {
  name = "heliox-${var.environment}-ecs-task-s3"
  role = aws_iam_role.ecs_task.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.s3_bucket_name}",
          "arn:aws:s3:::${var.s3_bucket_name}/*"
        ]
      }
    ]
  })
}

# CloudWatch Logs policy for task role
resource "aws_iam_role_policy" "ecs_task_logs" {
  name = "heliox-${var.environment}-ecs-task-logs"
  role = aws_iam_role.ecs_task.id
  
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "${var.log_group_arn}:*"
      }
    ]
  })
}

# API Task Definition
resource "aws_ecs_task_definition" "api" {
  family                   = "heliox-${var.environment}-api"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.api_image
      essential = true
      
      portMappings = [
        {
          containerPort = 8000
          protocol      = "tcp"
        }
      ]
      
      environment = [
        { name = "ENV", value = "production" },
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "FRONTEND_URL", value = var.frontend_url },
        { name = "CORS_ENABLED", value = "true" },
        { name = "CORS_ORIGINS", value = "[\"${var.frontend_url}\"]" }
      ]
      
      secrets = [
        { name = "SECRET_KEY", valueFrom = var.secret_key_arn },
        { name = "ADMIN_API_KEY", valueFrom = var.admin_api_key_arn },
        { name = "INTEGRATIONS_ENCRYPTION_KEY", valueFrom = var.integrations_encryption_key_arn },
        var.stripe_secret_key_arn != "" ? { name = "STRIPE_SECRET_KEY", valueFrom = var.stripe_secret_key_arn } : null,
        var.stripe_webhook_secret_arn != "" ? { name = "STRIPE_WEBHOOK_SECRET", valueFrom = var.stripe_webhook_secret_arn } : null,
        var.google_client_id_arn != "" ? { name = "GOOGLE_CLIENT_ID", valueFrom = var.google_client_id_arn } : null,
        var.google_client_secret_arn != "" ? { name = "GOOGLE_CLIENT_SECRET", valueFrom = var.google_client_secret_arn } : null
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "api"
        }
      }
      
      healthCheck = {
        command     = ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"]
        interval    = 30
        timeout     = 5
        retries     = 3
        startPeriod = 60
      }
    }
  ])
  
  tags = {
    Name        = "heliox-${var.environment}-api-task"
    Environment = var.environment
  }
}

# Worker Task Definition
resource "aws_ecs_task_definition" "worker" {
  family                   = "heliox-${var.environment}-worker"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name      = "worker"
      image     = var.worker_image
      essential = true
      command   = ["celery", "-A", "app.celery_app", "worker", "--loglevel=info"]
      
      environment = [
        { name = "ENV", value = "production" },
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url },
        { name = "FRONTEND_URL", value = var.frontend_url }
      ]
      
      secrets = [
        { name = "SECRET_KEY", valueFrom = var.secret_key_arn },
        { name = "ADMIN_API_KEY", valueFrom = var.admin_api_key_arn },
        { name = "INTEGRATIONS_ENCRYPTION_KEY", valueFrom = var.integrations_encryption_key_arn },
        var.stripe_secret_key_arn != "" ? { name = "STRIPE_SECRET_KEY", valueFrom = var.stripe_secret_key_arn } : null,
        var.google_client_id_arn != "" ? { name = "GOOGLE_CLIENT_ID", valueFrom = var.google_client_id_arn } : null,
        var.google_client_secret_arn != "" ? { name = "GOOGLE_CLIENT_SECRET", valueFrom = var.google_client_secret_arn } : null
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
  
  tags = {
    Name        = "heliox-${var.environment}-worker-task"
    Environment = var.environment
  }
}

# Beat (Scheduler) Task Definition
resource "aws_ecs_task_definition" "beat" {
  family                   = "heliox-${var.environment}-beat"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn
  
  container_definitions = jsonencode([
    {
      name      = "beat"
      image     = var.worker_image
      essential = true
      command   = ["celery", "-A", "app.celery_app", "beat", "--loglevel=info"]
      
      environment = [
        { name = "ENV", value = "production" },
        { name = "DATABASE_URL", value = var.database_url },
        { name = "REDIS_URL", value = var.redis_url }
      ]
      
      secrets = [
        { name = "SECRET_KEY", valueFrom = var.secret_key_arn },
        { name = "ADMIN_API_KEY", valueFrom = var.admin_api_key_arn },
        { name = "INTEGRATIONS_ENCRYPTION_KEY", valueFrom = var.integrations_encryption_key_arn }
      ]
      
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = var.log_group_name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = "beat"
        }
      }
    }
  ])
  
  tags = {
    Name        = "heliox-${var.environment}-beat-task"
    Environment = var.environment
  }
}

# API Service
resource "aws_ecs_service" "api" {
  name            = "heliox-${var.environment}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = "api"
    container_port   = 8000
  }
  
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }
  
  enable_execute_command = true
  
  tags = {
    Name        = "heliox-${var.environment}-api-service"
    Environment = var.environment
  }
  
  depends_on = [var.alb_target_group_arn]
}

# Worker Service
resource "aws_ecs_service" "worker" {
  name            = "heliox-${var.environment}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  deployment_configuration {
    maximum_percent         = 200
    minimum_healthy_percent = 100
  }
  
  enable_execute_command = true
  
  tags = {
    Name        = "heliox-${var.environment}-worker-service"
    Environment = var.environment
  }
}

# Beat Service (only 1 instance)
resource "aws_ecs_service" "beat" {
  name            = "heliox-${var.environment}-beat"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.beat.arn
  desired_count   = 1  # Always 1 for scheduler
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.ecs_tasks.id]
    assign_public_ip = false
  }
  
  deployment_configuration {
    maximum_percent         = 100
    minimum_healthy_percent = 0
  }
  
  enable_execute_command = true
  
  tags = {
    Name        = "heliox-${var.environment}-beat-service"
    Environment = var.environment
  }
}

# CloudWatch Alarms: CPU > 80%, Memory > 80%, 5xx errors
resource "aws_cloudwatch_metric_alarm" "api_cpu_high" {
  alarm_name          = "heliox-${var.environment}-api-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.api.name
  }

  alarm_description = "API service CPU utilization > 80%"
  alarm_actions      = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
  ok_actions         = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}

resource "aws_cloudwatch_metric_alarm" "api_memory_high" {
  alarm_name          = "heliox-${var.environment}-api-memory-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "MemoryUtilization"
  namespace           = "AWS/ECS"
  period              = 300
  statistic           = "Average"
  threshold           = 80

  dimensions = {
    ClusterName = aws_ecs_cluster.main.name
    ServiceName = aws_ecs_service.api.name
  }

  alarm_description = "API service memory utilization > 80%"
  alarm_actions      = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
  ok_actions         = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  count               = var.alb_arn_suffix != "" ? 1 : 0
  alarm_name          = "heliox-${var.environment}-alb-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 5

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
  }

  alarm_description = "ALB 5xx error rate elevated"
  alarm_actions      = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
  ok_actions         = var.alarm_sns_topic_arn != "" ? [var.alarm_sns_topic_arn] : []
}

# Auto Scaling for API Service
resource "aws_appautoscaling_target" "api" {
  max_capacity       = var.api_desired_count * 3
  min_capacity       = var.api_desired_count
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "heliox-${var.environment}-api-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  
  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}

data "aws_region" "current" {}
