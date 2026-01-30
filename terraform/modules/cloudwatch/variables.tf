variable "environment" {
  description = "Environment name"
  type        = string
}

variable "retention_in_days" {
  description = "Log retention in days"
  type        = number
  default     = 30
}
