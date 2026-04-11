# ── Network ───────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (ALB)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets (ECS, ElastiCache)"
  value       = aws_subnet.private[*].id
}

# ── ALB ───────────────────────────────────────────────────────────────────────

output "alb_dns_name" {
  description = "ALB DNS name (backend API)"
  value       = module.alb.dns_name
}

# ── Frontend ─────────────────────────────────────────────────────────────────

output "frontend_url" {
  description = "S3 website URL — this is the frontend"
  value       = module.frontend.website_url
}

output "frontend_s3_bucket" {
  description = "S3 bucket for frontend static files"
  value       = module.frontend.s3_bucket_name
}

# ── ElastiCache ───────────────────────────────────────────────────────────────

output "redis_url" {
  description = "Redis connection URL for ECS tasks and Celery workers"
  value       = module.elasticache.redis_url
}

# ── ECR ───────────────────────────────────────────────────────────────────────

output "ecr_api_image_url" {
  description = "ECR URL for the FastAPI image"
  value       = module.ecr.api_image_url
}

output "ecr_worker_image_url" {
  description = "ECR URL for the Celery worker image"
  value       = module.ecr.worker_image_url
}

# ── S3 ────────────────────────────────────────────────────────────────────────

output "s3_bucket_name" {
  description = "Name of the flair2 pipeline S3 bucket"
  value       = module.s3.bucket_name
}

# ── IAM ───────────────────────────────────────────────────────────────────────

output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role"
  value       = module.iam.ecs_execution_role_arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role (app permissions)"
  value       = module.iam.ecs_task_role_arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = module.iam.lambda_role_arn
}
