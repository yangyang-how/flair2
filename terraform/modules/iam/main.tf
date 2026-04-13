locals {
  prefix = "${var.project}-${var.env}"
}

# ── ECS Task Execution Role ───────────────────────────────────────────────────
# Used by the ECS agent (not the app) to:
#   - Pull images from ECR
#   - Write logs to CloudWatch
#   - Fetch secrets from Secrets Manager (kimi API key)

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

resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow execution role to read secrets (kimi API key injected via ECS secrets field)
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name = "${local.prefix}-ecs-execution-secrets"
  role = aws_iam_role.ecs_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = "arn:aws:secretsmanager:*:${var.account_id}:secret:${var.project}/*"
    }]
  })
}

# ── ECS Task Role ─────────────────────────────────────────────────────────────
# Used by the application code running inside containers to access AWS services:
#   - S3 (pipeline assets)
#   - DynamoDB (pipeline runs + video performance tables)
#   - CloudWatch logs

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

resource "aws_iam_role_policy" "ecs_task_permissions" {
  name = "${local.prefix}-ecs-task-permissions"
  role = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project}-pipeline-${var.env}",
          "arn:aws:s3:::${var.project}-pipeline-${var.env}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem",
          "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:${var.account_id}:table/${var.project}-${var.env}-*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream", "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:${var.account_id}:log-group:/ecs/${local.prefix}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel"
        ]
        Resource = "*"
      }
    ]
  })
}

# ── Lambda Execution Role ─────────────────────────────────────────────────────
# Used by the Lambda function (S7 video generation) to:
#   - Write logs to CloudWatch
#   - Read/write S3

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

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_s3" {
  name = "${local.prefix}-lambda-s3"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject"]
      Resource = [
        "arn:aws:s3:::${var.project}-pipeline-${var.env}/*"
      ]
    }]
  })
}
