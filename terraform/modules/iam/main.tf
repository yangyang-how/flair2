locals {
  prefix = "${var.project}-${var.env}"
}

# ── ECS Task Execution Role ───────────────────────────────────────────────────
# Used by the ECS agent itself (not the app code) to:
# - Pull images from ECR
# - Write logs to CloudWatch

resource "aws_iam_role" "ecs_execution" {
  name = "${local.prefix}-ecs-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.prefix}-ecs-execution-role" }
}

# AWS managed policy: ECR pull + CloudWatch logs
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ── ECS Task Role ─────────────────────────────────────────────────────────────
# Used by the app code running inside the container (FastAPI + Celery workers) to:
# - Read/write S3 (pipeline results, dataset, generated videos)
# - Read/write DynamoDB (pipeline_runs, video_performance tables)
# - Write CloudWatch logs (structured logging)
# Note: ElastiCache Redis access is network-only (no IAM needed)

resource "aws_iam_role" "ecs_task" {
  name = "${local.prefix}-ecs-task-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.prefix}-ecs-task-role" }
}

resource "aws_iam_policy" "ecs_task_policy" {
  name        = "${local.prefix}-ecs-task-policy"
  description = "Least-privilege policy for flair2 ECS tasks (API + Celery workers)"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3PipelineBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project}-pipeline-*",
          "arn:aws:s3:::${var.project}-pipeline-*/*"
        ]
      },
      {
        Sid    = "DynamoDBTables"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/${var.project}-${var.env}-pipeline-runs",
          "arn:aws:dynamodb:*:*:table/${var.project}-${var.env}-video-performance"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/ecs/${local.prefix}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_task_policy" {
  role       = aws_iam_role.ecs_task.name
  policy_arn = aws_iam_policy.ecs_task_policy.arn
}

# ── Lambda Execution Role ─────────────────────────────────────────────────────
# Used by the S7 video generation Lambda to:
# - Write generated video clips to S3
# - Write logs to CloudWatch

resource "aws_iam_role" "lambda" {
  name = "${local.prefix}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = { Name = "${local.prefix}-lambda-role" }
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "${local.prefix}-lambda-policy"
  description = "Least-privilege policy for flair2 S7 video generation Lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3VideoWrite"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject"
        ]
        Resource = "arn:aws:s3:::${var.project}-pipeline-*/runs/*/videos/*"
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_policy" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}
