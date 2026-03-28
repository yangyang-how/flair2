output "bucket_name" {
  description = "Name of the flair2 pipeline S3 bucket"
  value       = aws_s3_bucket.pipeline.bucket
}

output "bucket_arn" {
  description = "ARN of the flair2 pipeline S3 bucket"
  value       = aws_s3_bucket.pipeline.arn
}
