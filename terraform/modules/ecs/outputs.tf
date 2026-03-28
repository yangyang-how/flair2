output "cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "cluster_arn" {
  description = "ECS cluster ARN"
  value       = aws_ecs_cluster.main.arn
}

output "api_service_name" {
  description = "ECS API service name"
  value       = aws_ecs_service.api.name
}

output "worker_service_name" {
  description = "ECS Celery worker service name"
  value       = aws_ecs_service.worker.name
}

output "api_log_group" {
  description = "CloudWatch log group for API tasks"
  value       = aws_cloudwatch_log_group.api.name
}

output "worker_log_group" {
  description = "CloudWatch log group for Celery worker tasks"
  value       = aws_cloudwatch_log_group.worker.name
}
