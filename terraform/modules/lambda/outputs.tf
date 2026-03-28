output "function_name" {
  description = "Lambda function name for S7 video generation"
  value       = var.enable_lambda ? aws_lambda_function.s7_video_gen[0].function_name : null
}

output "function_arn" {
  description = "Lambda function ARN"
  value       = var.enable_lambda ? aws_lambda_function.s7_video_gen[0].arn : null
}

output "invoke_arn" {
  description = "Lambda invoke ARN (used for API Gateway integration if added later)"
  value       = var.enable_lambda ? aws_lambda_function.s7_video_gen[0].invoke_arn : null
}
