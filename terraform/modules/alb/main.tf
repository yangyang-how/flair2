locals {
  prefix = "${var.project}-${var.env}"
}

# ── Application Load Balancer ─────────────────────────────────────────────────
# Internet-facing ALB in public subnets.
# Terminates HTTPS from Cloudflare Pages and forwards to ECS API tasks.

resource "aws_lb" "main" {
  name               = "${local.prefix}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.security_group_id]
  subnets            = var.public_subnet_ids

  tags = { Name = "${local.prefix}-alb" }
}

# ── Target Group ──────────────────────────────────────────────────────────────
# Routes traffic to ECS API tasks on port 8000.
# Health check hits /api/health which FastAPI exposes.

resource "aws_lb_target_group" "api" {
  name        = "${local.prefix}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip" # Required for Fargate (tasks have IPs, not instance IDs)

  health_check {
    path                = "/api/health"
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
    matcher             = "200"
  }

  tags = { Name = "${local.prefix}-api-tg" }
}

# ── Listeners ─────────────────────────────────────────────────────────────────

# HTTP listener — redirect all traffic to HTTPS
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# HTTPS listener — forward to API target group
# Certificate must be provisioned in ACM before apply (outside Terraform scope)
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.acm_certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}
