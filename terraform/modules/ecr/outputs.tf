output "api_image_url" {
  description = "ECR repository URL for the FastAPI image"
  value       = aws_ecr_repository.api.repository_url
}

output "worker_image_url" {
  description = "ECR repository URL for the Celery worker image"
  value       = aws_ecr_repository.worker.repository_url
}

output "api_repository_name" {
  description = "ECR repository name for the FastAPI image"
  value       = aws_ecr_repository.api.name
}

output "worker_repository_name" {
  description = "ECR repository name for the Celery worker image"
  value       = aws_ecr_repository.worker.name
}
