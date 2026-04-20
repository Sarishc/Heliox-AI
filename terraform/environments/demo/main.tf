/**
 * Heliox Demo Environment — ECS Service
 *
 * Runs the same Docker image as production with DEMO_MODE=true and a
 * separate RDS database (heliox_demo).  Serves demo.heliox.ai via a
 * dedicated ALB listener rule and Route 53 record.
 *
 * Prerequisites (shared with production environment):
 *   - VPC, subnets, security groups
 *   - ECR repository with the Heliox backend image
 *   - RDS cluster (a separate DB named heliox_demo is created here)
 *   - ElastiCache Redis cluster
 *   - ACM certificate covering *.heliox.ai
 *   - Existing ALB (shared)
 *   - IAM execution role with ECR pull + Secrets Manager read
 */

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Store state separately from production
  backend "s3" {
    bucket         = "heliox-terraform-state"
    key            = "demo/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "heliox-terraform-locks"
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Variables ─────────────────────────────────────────────────────────────────

variable "aws_region"          { default = "us-east-1" }
variable "vpc_id"              { description = "Shared VPC ID" }
variable "private_subnet_ids"  { type = list(string); description = "Private subnets for ECS tasks" }
variable "public_subnet_ids"   { type = list(string); description = "Public subnets for ALB" }
variable "alb_arn"             { description = "Shared ALB ARN" }
variable "alb_listener_arn"    { description = "HTTPS listener ARN on the shared ALB" }
variable "ecs_cluster_arn"     { description = "Shared ECS cluster ARN" }
variable "ecr_image_uri"       { description = "Full ECR image URI (e.g. 123456789.dkr.ecr.us-east-1.amazonaws.com/heliox:latest)" }
variable "ecs_execution_role_arn" { description = "ECS task execution role ARN" }
variable "redis_url"           { description = "ElastiCache Redis URL (shared)" }
variable "rds_endpoint"        { description = "RDS cluster endpoint (shared)" }
variable "rds_password"        { sensitive = true; description = "RDS password for demo DB user" }
variable "secret_key"          { sensitive = true; description = "JWT secret for demo environment" }
variable "admin_api_key"       { sensitive = true; description = "Admin API key for seeding" }
variable "encryption_key"      { sensitive = true; description = "Fernet key for integration token encryption" }
variable "demo_tenant_id"      { default = ""; description = "UUID of the seeded demo tenant (set after first seed)" }
variable "acm_certificate_arn" { description = "ACM certificate ARN for *.heliox.ai" }
variable "route53_zone_id"     { description = "Route 53 hosted zone ID for heliox.ai" }

locals {
  name_prefix  = "heliox-demo"
  demo_db_name = "heliox_demo"
  demo_host    = "demo.heliox.ai"
}

# ── Demo database (separate from production) ──────────────────────────────────

resource "aws_db_instance" "demo" {
  identifier             = "${local.name_prefix}-postgres"
  engine                 = "postgres"
  engine_version         = "15.4"
  instance_class         = "db.t3.micro"
  allocated_storage      = 20
  db_name                = local.demo_db_name
  username               = "heliox_demo"
  password               = var.rds_password
  vpc_security_group_ids = [aws_security_group.demo_ecs.id]
  db_subnet_group_name   = aws_db_subnet_group.demo.name
  skip_final_snapshot    = true
  deletion_protection    = false  # demo DB can be recreated
  backup_retention_period = 1

  tags = { Name = "${local.name_prefix}-postgres", Environment = "demo" }
}

resource "aws_db_subnet_group" "demo" {
  name       = "${local.name_prefix}-subnet-group"
  subnet_ids = var.private_subnet_ids
  tags       = { Name = "${local.name_prefix}-subnet-group" }
}

# ── Security group ─────────────────────────────────────────────────────────────

resource "aws_security_group" "demo_ecs" {
  name        = "${local.name_prefix}-ecs-sg"
  description = "Demo ECS tasks — allow ALB inbound, all outbound"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    description = "ALB → ECS"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${local.name_prefix}-ecs-sg", Environment = "demo" }
}

# ── ECS task definition ────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "demo" {
  name              = "/ecs/${local.name_prefix}"
  retention_in_days = 7
  tags              = { Environment = "demo" }
}

resource "aws_ecs_task_definition" "demo" {
  family                   = local.name_prefix
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "512"   # 0.5 vCPU
  memory                   = "1024"  # 1 GB RAM
  execution_role_arn       = var.ecs_execution_role_arn
  task_role_arn            = var.ecs_execution_role_arn

  container_definitions = jsonencode([
    {
      name      = "heliox-demo"
      image     = var.ecr_image_uri
      essential = true

      portMappings = [{ containerPort = 8000, protocol = "tcp" }]

      environment = [
        { name = "ENV",                value = "production" },
        { name = "DEMO_MODE",          value = "true" },
        { name = "DEMO_TENANT_ID",     value = var.demo_tenant_id },
        { name = "DEMO_SIGNUP_URL",    value = "https://app.heliox.ai/signup" },
        { name = "DATABASE_URL",       value = "postgresql+psycopg2://heliox_demo:${var.rds_password}@${aws_db_instance.demo.endpoint}/${local.demo_db_name}" },
        { name = "REDIS_URL",          value = var.redis_url },
        { name = "SECRET_KEY",         value = var.secret_key },
        { name = "ADMIN_API_KEY",      value = var.admin_api_key },
        { name = "INTEGRATIONS_ENCRYPTION_KEY", value = var.encryption_key },
        { name = "MULTI_TENANT",       value = "true" },
        { name = "CORS_ORIGINS",       value = "[\"https://demo.heliox.ai\",\"https://app.heliox.ai\"]" },
        { name = "API_BASE_URL",       value = "https://demo.heliox.ai" },
        { name = "FRONTEND_URL",       value = "https://app.heliox.ai" },
        { name = "LOG_JSON_FORMAT",    value = "true" },
        { name = "LOG_LEVEL",          value = "INFO" },
        { name = "AUTH_COOKIE_SECURE", value = "true" },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.demo.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "ecs"
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

  tags = { Name = local.name_prefix, Environment = "demo" }
}

# ── ECS service ───────────────────────────────────────────────────────────────

resource "aws_ecs_service" "demo" {
  name            = local.name_prefix
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.demo.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.demo_ecs.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.demo.arn
    container_name   = "heliox-demo"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener_rule.demo]

  tags = { Name = local.name_prefix, Environment = "demo" }
}

# ── ALB target group + listener rule ──────────────────────────────────────────

resource "aws_lb_target_group" "demo" {
  name        = "${local.name_prefix}-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = { Name = "${local.name_prefix}-tg", Environment = "demo" }
}

resource "aws_lb_listener_rule" "demo" {
  listener_arn = var.alb_listener_arn
  priority     = 200

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.demo.arn
  }

  condition {
    host_header { values = [local.demo_host] }
  }

  tags = { Name = "${local.name_prefix}-rule", Environment = "demo" }
}

# ── Route 53 record ───────────────────────────────────────────────────────────

data "aws_lb" "shared" {
  arn = var.alb_arn
}

resource "aws_route53_record" "demo" {
  zone_id = var.route53_zone_id
  name    = local.demo_host
  type    = "A"

  alias {
    name                   = data.aws_lb.shared.dns_name
    zone_id                = data.aws_lb.shared.zone_id
    evaluate_target_health = true
  }
}

# ── One-time seed task (ECS Run Task on first deploy) ─────────────────────────
# Run manually after first deploy once DEMO_TENANT_ID is empty:
#
#   aws ecs run-task \
#     --cluster <CLUSTER_ARN> \
#     --task-definition heliox-demo \
#     --overrides '{"containerOverrides":[{"name":"heliox-demo","command":["python","-m","scripts.run_demo_seed"]}]}' \
#     --launch-type FARGATE \
#     --network-configuration "awsvpcConfiguration={subnets=[...],securityGroups=[...],assignPublicIp=DISABLED}"
#
# Then copy DEMO_TENANT_ID from the response and set var.demo_tenant_id.

# ── Outputs ───────────────────────────────────────────────────────────────────

output "demo_url" {
  value       = "https://${local.demo_host}"
  description = "Demo environment URL"
}

output "demo_db_endpoint" {
  value       = aws_db_instance.demo.endpoint
  description = "Demo RDS endpoint"
}

output "demo_ecs_service_arn" {
  value       = aws_ecs_service.demo.id
  description = "Demo ECS service ARN"
}

output "demo_log_group" {
  value       = aws_cloudwatch_log_group.demo.name
  description = "CloudWatch log group for demo service"
}
