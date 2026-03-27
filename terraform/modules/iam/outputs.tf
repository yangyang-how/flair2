output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role (used by ECS agent to pull images + write logs)"
  value       = aws_iam_role.ecs_execution.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role (used by app code for S3, DynamoDB access)"
  value       = aws_iam_role.ecs_task.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role (used by S7 video generation function)"
  value       = aws_iam_role.lambda.arn
}
