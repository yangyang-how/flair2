output "website_url" {
  description = "S3 website URL — this is the frontend"
  value       = "http://${aws_s3_bucket_website_configuration.frontend.website_endpoint}"
}

output "s3_bucket_name" {
  description = "S3 bucket name for frontend static files"
  value       = aws_s3_bucket.frontend.bucket
}
