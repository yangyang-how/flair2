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
  description = "Initial number of API task replicas (AppAutoScaling manages count after first apply)"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Initial number of Celery worker task replicas (AppAutoScaling manages count after first apply)"
  type        = number
  default     = 2
}

variable "api_min_count" {
  description = "Minimum number of API tasks — AppAutoScaling will never scale below this"
  type        = number
  default     = 2
}

variable "api_max_count" {
  description = "Maximum number of API tasks — AppAutoScaling will never scale above this. Learner Lab default Fargate quota is 6 vCPUs; keep api_max_count × (api_cpu/1024) + worker_max_count × (worker_cpu/1024) ≤ 6."
  type        = number
  default     = 6
}

variable "worker_min_count" {
  description = "Minimum number of Celery worker tasks"
  type        = number
  default     = 2
}

variable "worker_max_count" {
  description = "Maximum number of Celery worker tasks. See api_max_count note on Fargate vCPU quota."
  type        = number
  default     = 4
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
