output "function_name" {
  description = "Lambda function name for S7 video generation"
  value       = aws_lambda_function.s7_video_gen.function_name
}

output "function_arn" {
  description = "Lambda function ARN"
  value       = aws_lambda_function.s7_video_gen.arn
}

output "invoke_arn" {
  description = "Lambda invoke ARN (used for API Gateway integration if added later)"
  value       = aws_lambda_function.s7_video_gen.invoke_arn
}
