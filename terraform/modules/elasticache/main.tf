locals {
  prefix = "${var.project}-${var.env}"
}

# Subnet group — ElastiCache must know which private subnets it can use
resource "aws_elasticache_subnet_group" "main" {
  name       = "${local.prefix}-redis-subnet-group"
  subnet_ids = var.subnet_ids

  tags = { Name = "${local.prefix}-redis-subnet-group" }
}

# Single-node Redis cluster
# Single node is sufficient for a course project — no replication needed.
# The orchestrator state machine (DDIA Ch.5 reference) stores run state here.
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${local.prefix}-redis"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = var.node_type
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = var.security_group_ids

  # Disable automatic backups — course project, data is ephemeral
  snapshot_retention_limit = 0

  tags = { Name = "${local.prefix}-redis" }
}
