output "ecs_execution_role_arn" {
  description = "ARN of the ECS task execution role (LabRole — Learner Lab pre-provisioned)"
  value       = data.aws_iam_role.lab_role.arn
}

output "ecs_task_role_arn" {
  description = "ARN of the ECS task role (LabRole — Learner Lab pre-provisioned)"
  value       = data.aws_iam_role.lab_role.arn
}

output "lambda_role_arn" {
  description = "ARN of the Lambda execution role (LabRole — Learner Lab pre-provisioned)"
  value       = data.aws_iam_role.lab_role.arn
}
