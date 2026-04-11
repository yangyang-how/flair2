locals {
  prefix = "${var.project}-${var.env}"
}

# ── ECS Cluster ───────────────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${local.prefix}-cluster"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = { Name = "${local.prefix}-cluster" }
}

# ── CloudWatch Log Groups ─────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.prefix}/api"
  retention_in_days = 7

  tags = { Name = "${local.prefix}-api-logs" }
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${local.prefix}/worker"
  retention_in_days = 7

  tags = { Name = "${local.prefix}-worker-logs" }
}

# ── API Task Definition ───────────────────────────────────────────────────────
# Runs the FastAPI server (uvicorn app.main:app)

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.prefix}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.api_cpu
  memory                   = var.api_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "api"
    image     = var.ecr_api_image_url
    essential = true

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [
      { name = "FLAIR2_REDIS_URL", value = "${var.redis_url}/0" },
      { name = "FLAIR2_CELERY_BROKER_URL", value = "${var.redis_url}/1" },
      { name = "FLAIR2_S3_BUCKET", value = var.s3_bucket_name },
      { name = "FLAIR2_AWS_REGION", value = var.aws_region },
      { name = "FLAIR2_DYNAMODB_RUNS_TABLE", value = "${var.project}-${var.env}-pipeline-runs" },
      { name = "FLAIR2_DYNAMODB_PERF_TABLE", value = "${var.project}-${var.env}-video-performance" },
      { name = "FLAIR2_ENVIRONMENT", value = var.env },
      { name = "FLAIR2_CORS_ORIGINS", value = var.cors_origins }
    ]

    secrets = [
      { name = "FLAIR2_KIMI_API_KEY", valueFrom = var.kimi_api_key_secret_arn }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.api.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "api"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 10
    }
  }])

  tags = { Name = "${local.prefix}-api-task" }
}

# ── API Service ───────────────────────────────────────────────────────────────
# 2 replicas behind the ALB target group

resource "aws_ecs_service" "api" {
  name            = "${local.prefix}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.api_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = "api"
    container_port   = 8000
  }

  # Terraform manages infrastructure; CI/CD manages deployments.
  # ignore_changes on task_definition prevents terraform apply from reverting
  # the service to the original placeholder image after CI/CD has deployed a
  # real image. New task definition revisions are rolled out by ECS via CI/CD
  # (push to ECR → update service), not by Terraform.
  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = { Name = "${local.prefix}-api-service" }
}

# ── Celery Worker Task Definition ─────────────────────────────────────────────
# Same image as API, different command: runs Celery worker instead of uvicorn.
# Workers pull tasks from Redis (BRPOP) and execute S1/S4 stage functions.

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.prefix}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.worker_cpu
  memory                   = var.worker_memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([{
    name      = "worker"
    image     = var.ecr_worker_image_url
    essential = true

    # Override CMD to start Celery instead of FastAPI
    command = [
      "celery", "-A", "app.workers.celery_app", "worker",
      "--loglevel=info", "--concurrency=4"
    ]

    environment = [
      { name = "FLAIR2_REDIS_URL", value = "${var.redis_url}/0" },
      { name = "FLAIR2_CELERY_BROKER_URL", value = "${var.redis_url}/1" },
      { name = "FLAIR2_S3_BUCKET", value = var.s3_bucket_name },
      { name = "FLAIR2_AWS_REGION", value = var.aws_region },
      { name = "FLAIR2_DYNAMODB_RUNS_TABLE", value = "${var.project}-${var.env}-pipeline-runs" },
      { name = "FLAIR2_DYNAMODB_PERF_TABLE", value = "${var.project}-${var.env}-video-performance" },
      { name = "FLAIR2_ENVIRONMENT", value = var.env }
    ]

    secrets = [
      { name = "FLAIR2_KIMI_API_KEY", valueFrom = var.kimi_api_key_secret_arn }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.worker.name
        "awslogs-region"        = var.aws_region
        "awslogs-stream-prefix" = "worker"
      }
    }
  }])

  tags = { Name = "${local.prefix}-worker-task" }
}

# ── Celery Worker Service ─────────────────────────────────────────────────────
# No ALB — workers pull work from Redis, no inbound traffic needed

resource "aws_ecs_service" "worker" {
  name            = "${local.prefix}-worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.worker_desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [var.security_group_id]
    assign_public_ip = false
  }

  # Same deployment model as API service — CI/CD owns image rollouts.
  lifecycle {
    ignore_changes = [task_definition]
  }

  tags = { Name = "${local.prefix}-worker-service" }
}
