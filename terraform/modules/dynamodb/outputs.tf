output "pipeline_runs_table_name" {
  description = "Name of the pipeline_runs DynamoDB table"
  value       = aws_dynamodb_table.pipeline_runs.name
}

output "pipeline_runs_table_arn" {
  description = "ARN of the pipeline_runs DynamoDB table"
  value       = aws_dynamodb_table.pipeline_runs.arn
}

output "video_performance_table_name" {
  description = "Name of the video_performance DynamoDB table"
  value       = aws_dynamodb_table.video_performance.name
}

output "video_performance_table_arn" {
  description = "ARN of the video_performance DynamoDB table"
  value       = aws_dynamodb_table.video_performance.arn
}
