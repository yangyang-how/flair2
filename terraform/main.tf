terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state in S3 — bucket must be created manually before first apply.
  # The key is a partial configuration — pass the env-specific key at init time:
  #   terraform init -backend-config="key=env/dev/terraform.tfstate"
  #   terraform init -backend-config="key=env/prod/terraform.tfstate"
  # This keeps dev and prod state isolated in the same bucket.
  backend "s3" {
    bucket = "flair2-terraform-state"
    key    = "env/dev/terraform.tfstate"
    region = "us-west-2"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}

# ── VPC ──────────────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project}-${var.env}-vpc" }
}

# ── Subnets ───────────────────────────────────────────────────────────────────

# Public subnets — ALB lives here (internet-facing)
resource "aws_subnet" "public" {
  count             = length(var.public_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.public_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  map_public_ip_on_launch = true

  tags = { Name = "${var.project}-${var.env}-public-${count.index + 1}" }
}

# Private subnets — ECS tasks and ElastiCache live here (no direct internet access)
resource "aws_subnet" "private" {
  count             = length(var.private_subnet_cidrs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = var.private_subnet_cidrs[count.index]
  availability_zone = var.availability_zones[count.index]

  tags = { Name = "${var.project}-${var.env}-private-${count.index + 1}" }
}

# ── Internet Gateway ──────────────────────────────────────────────────────────

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = { Name = "${var.project}-${var.env}-igw" }
}

# ── NAT Gateway ───────────────────────────────────────────────────────────────
# ECS tasks in private subnets need outbound internet to reach Gemini/Kimi APIs.
# One NAT gateway in the first public subnet is enough for a course project.

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = { Name = "${var.project}-${var.env}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = { Name = "${var.project}-${var.env}-nat" }

  depends_on = [aws_internet_gateway.main]
}

# ── Route Tables ──────────────────────────────────────────────────────────────

# Public route table — sends all traffic to internet gateway
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${var.project}-${var.env}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private route table — sends all traffic through NAT gateway
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${var.project}-${var.env}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ── Security Groups ───────────────────────────────────────────────────────────

# ALB — accepts HTTPS from internet, forwards to ECS API
resource "aws_security_group" "alb" {
  name        = "${var.project}-${var.env}-alb-sg"
  description = "ALB: accept HTTP/HTTPS from internet"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "All outbound"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.env}-alb-sg" }
}

# ECS tasks (API + Celery worker) — accept traffic from ALB only, reach out to internet via NAT
resource "aws_security_group" "ecs" {
  name        = "${var.project}-${var.env}-ecs-sg"
  description = "ECS tasks: accept from ALB, reach internet via NAT"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "From ALB"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    description = "All outbound (Gemini/Kimi APIs, AWS services)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-${var.env}-ecs-sg" }
}

# ElastiCache Redis — accept only from ECS tasks
resource "aws_security_group" "elasticache" {
  name        = "${var.project}-${var.env}-elasticache-sg"
  description = "ElastiCache Redis: accept from ECS tasks only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Redis from ECS"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [aws_security_group.ecs.id]
  }

  tags = { Name = "${var.project}-${var.env}-elasticache-sg" }
}

# ── Modules ───────────────────────────────────────────────────────────────────

module "iam" {
  source  = "./modules/iam"
  project = var.project
  env     = var.env
}

module "s3" {
  source  = "./modules/s3"
  project = var.project
  env     = var.env
}

module "dynamodb" {
  source  = "./modules/dynamodb"
  project = var.project
  env     = var.env
}

module "ecr" {
  source  = "./modules/ecr"
  project = var.project
  env     = var.env
}

module "elasticache" {
  source             = "./modules/elasticache"
  project            = var.project
  env                = var.env
  subnet_ids         = aws_subnet.private[*].id
  security_group_ids = [aws_security_group.elasticache.id]
}

module "alb" {
  source              = "./modules/alb"
  project             = var.project
  env                 = var.env
  vpc_id              = aws_vpc.main.id
  public_subnet_ids   = aws_subnet.public[*].id
  security_group_id   = aws_security_group.alb.id
  acm_certificate_arn = var.acm_certificate_arn
}

module "ecs" {
  source                    = "./modules/ecs"
  project                   = var.project
  env                       = var.env
  aws_region                = var.aws_region
  vpc_id                    = aws_vpc.main.id
  private_subnet_ids        = aws_subnet.private[*].id
  security_group_id         = aws_security_group.ecs.id
  execution_role_arn        = module.iam.ecs_execution_role_arn
  task_role_arn             = module.iam.ecs_task_role_arn
  alb_target_group_arn      = module.alb.target_group_arn
  redis_url                 = module.elasticache.redis_url
  s3_bucket_name            = module.s3.bucket_name
  ecr_api_image_url         = module.ecr.api_image_url
  ecr_worker_image_url      = module.ecr.worker_image_url
  kimi_api_key_secret_arn   = var.kimi_api_key_secret_arn
  gemini_api_key_secret_arn = var.gemini_api_key_secret_arn
}

module "lambda" {
  source             = "./modules/lambda"
  project            = var.project
  env                = var.env
  execution_role_arn = module.iam.lambda_role_arn
  s3_bucket_name     = module.s3.bucket_name
}
