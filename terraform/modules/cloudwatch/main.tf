/**
 * CloudWatch Module
 * Creates CloudWatch log group for ECS tasks
 */

resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/heliox-${var.environment}"
  retention_in_days = var.retention_in_days
  
  tags = {
    Name        = "heliox-${var.environment}-logs"
    Environment = var.environment
  }
}

# CloudWatch Dashboard (optional)
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "heliox-${var.environment}"
  
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ECS", "CPUUtilization", { stat = "Average" }],
            [".", "MemoryUtilization", { stat = "Average" }]
          ]
          period = 300
          stat   = "Average"
          region = data.aws_region.current.name
          title  = "ECS Resource Utilization"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApplicationELB", "TargetResponseTime", { stat = "Average" }],
            [".", "RequestCount", { stat = "Sum" }]
          ]
          period = 300
          stat   = "Average"
          region = data.aws_region.current.name
          title  = "ALB Metrics"
        }
      }
    ]
  })
}

data "aws_region" "current" {}
