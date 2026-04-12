variable "account_id" {
  description = "AWS account ID — used to scope IAM policy resource ARNs"
  type        = string
}

variable "project" {
  description = "Project name — used as a prefix for all resource names"
  type        = string
  default     = "flair2"
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod"
  }
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-2"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ) — used by ALB"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ) — used by ECS and ElastiCache"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "availability_zones" {
  description = "AZs to spread subnets across (must match subnet CIDR count)"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b"]
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener. Leave empty for HTTP-only (e.g. Learner Lab)."
  type        = string
  default     = ""
}

variable "kimi_api_key_secret_arn" {
  description = "Secrets Manager ARN for the Kimi API key — create manually before apply: aws secretsmanager create-secret --name flair2/dev/kimi-api-key"
  type        = string
}


variable "cors_origins" {
  description = "Comma-separated CORS origins for the API (e.g. https://flair2.pages.dev)"
  type        = string
  default     = ""
}

# ── ECS Autoscaling ───────────────────────────────────────────────────────────

variable "api_min_count" {
  description = "Minimum number of API tasks for AppAutoScaling"
  type        = number
  default     = 2
}

variable "api_max_count" {
  description = "Maximum number of API tasks for AppAutoScaling. Learner Lab Fargate quota is ~6 vCPUs — keep api_max × 0.5 + worker_max × 1 ≤ 6."
  type        = number
  default     = 6
}

variable "worker_min_count" {
  description = "Minimum number of Celery worker tasks for AppAutoScaling"
  type        = number
  default     = 2
}

variable "worker_max_count" {
  description = "Maximum number of Celery worker tasks for AppAutoScaling. See api_max_count note on Fargate vCPU quota."
  type        = number
  default     = 4
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

variable "elasticache_node_type" {
  description = "ElastiCache node type. Use cache.t3.micro for dev; upgrade to cache.r6g.large for load testing."
  type        = string
  default     = "cache.t3.micro"
}
