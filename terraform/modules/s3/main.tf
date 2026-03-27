locals {
  bucket_name = "${var.project}-pipeline-${var.env}"
}

resource "aws_s3_bucket" "pipeline" {
  bucket = local.bucket_name

  tags = { Name = local.bucket_name }
}

# Block all public access — presigned URLs are used for frontend access
resource "aws_s3_bucket_public_access_block" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning off — pipeline results are write-once, cost savings for course project
resource "aws_s3_bucket_versioning" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  versioning_configuration {
    status = "Disabled"
  }
}

# Lifecycle: auto-delete run artifacts after 30 days to control storage costs
resource "aws_s3_bucket_lifecycle_configuration" "pipeline" {
  bucket = aws_s3_bucket.pipeline.id

  rule {
    id     = "expire-run-artifacts"
    status = "Enabled"

    filter {
      prefix = "runs/"
    }

    expiration {
      days = 30
    }
  }
}
