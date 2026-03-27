locals {
  prefix        = "${var.project}-${var.env}"
  function_name = "${local.prefix}-s7-video-gen"
}

# ── CloudWatch Log Group ──────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = 7

  tags = { Name = "${local.function_name}-logs" }
}

# ── Lambda Function ───────────────────────────────────────────────────────────
# S7: on-demand video generation triggered by the user selecting 1-3 scripts.
# Calls Seedance/Veo API, polls for completion, writes video to S3.
#
# Deployed as a ZIP package — CI/CD uploads the package to S3 before apply.
# Using a placeholder ZIP here so Terraform can create the function on first apply;
# actual code is deployed separately via CI/CD (aws lambda update-function-code).

resource "aws_lambda_function" "s7_video_gen" {
  function_name = local.function_name
  role          = var.execution_role_arn

  # Placeholder — CI/CD replaces this with the real deployment package
  filename      = "${path.module}/placeholder.zip"
  handler       = "handler.lambda_handler"
  runtime       = "python3.11"

  timeout     = var.timeout
  memory_size = var.memory_size

  environment {
    variables = {
      S3_BUCKET = var.s3_bucket_name
      ENV       = var.env
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda]

  tags = { Name = local.function_name }
}
