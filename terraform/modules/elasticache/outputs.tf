output "redis_url" {
  description = "Redis connection URL (used by ECS tasks as REDIS_URL env var)"
  value       = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:${aws_elasticache_cluster.redis.port}"
}

output "redis_host" {
  description = "Redis endpoint hostname"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "redis_port" {
  description = "Redis port"
  value       = aws_elasticache_cluster.redis.port
}
