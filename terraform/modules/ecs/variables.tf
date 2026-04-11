variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
}

variable "vpc_id" {
  description = "VPC ID"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for ECS tasks"
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group ID for ECS tasks"
  type        = string
}

variable "execution_role_arn" {
  description = "ECS task execution role ARN (pull ECR images, write logs)"
  type        = string
}

variable "task_role_arn" {
  description = "ECS task role ARN (app permissions: S3, DynamoDB)"
  type        = string
}

variable "alb_target_group_arn" {
  description = "ALB target group ARN for the API service"
  type        = string
}

variable "redis_url" {
  description = "Redis connection URL for Celery broker and pipeline state"
  type        = string
}

variable "s3_bucket_name" {
  description = "S3 bucket name for pipeline results"
  type        = string
}

variable "ecr_api_image_url" {
  description = "ECR image URL for the FastAPI service"
  type        = string
}

variable "ecr_worker_image_url" {
  description = "ECR image URL for the Celery worker service"
  type        = string
}

variable "api_desired_count" {
  description = "Number of API task replicas"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Number of Celery worker task replicas"
  type        = number
  default     = 2
}

variable "api_cpu" {
  description = "CPU units for API task (1024 = 1 vCPU)"
  type        = number
  default     = 512
}

variable "api_memory" {
  description = "Memory (MB) for API task"
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "CPU units for Celery worker task"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Memory (MB) for Celery worker task"
  type        = number
  default     = 2048
}

variable "aws_region" {
  description = "AWS region — used for CloudWatch log configuration"
  type        = string
  default     = "us-west-2"
}

variable "cors_origins" {
  description = "Comma-separated CORS origins for the API (e.g. Cloudflare Pages URL)"
  type        = string
  default     = ""
}

variable "kimi_api_key_secret_arn" {
  description = "Secrets Manager ARN for the Kimi (Moonshot) API key"
  type        = string
}

variable "gemini_api_key_secret_arn" {
  description = "Secrets Manager ARN for the Gemini API key (video generation only)"
  type        = string
}
