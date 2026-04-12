project    = "flair2"
env        = "dev"
account_id = "314727362981"

aws_region = "us-west-2"

vpc_cidr             = "10.0.0.0/16"
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.11.0/24", "10.0.12.0/24"]
availability_zones   = ["us-west-2a", "us-west-2b"]

# Create the Kimi API key secret manually before apply:
#   aws secretsmanager create-secret --name flair2/dev/kimi-api-key --secret-string "YOUR_KEY"
# Then paste the ARN returned by the command here.
kimi_api_key_secret_arn = "arn:aws:secretsmanager:us-west-2:314727362981:secret:flair2/dev/kimi-api-key-JNzWmi"

# ── ECS Autoscaling ───────────────────────────────────────────────────────────
# AppAutoScaling keeps tasks between min and max based on CPU utilisation.
# For load testing at K=10000 raise api_max_count to 50 and worker_max_count to 30.
# Learner Lab Fargate quota: ~6 on-demand vCPUs per region.
# api_max  × 0.5 vCPU = 3 vCPU
# worker_max × 1 vCPU = 4 vCPU
# Peak total           = 7 vCPU (worst case, unlikely both hit max simultaneously)
# Demonstrates scale-out from 2→4+ tasks; mechanism is identical to 2→50.
api_min_count    = 2
api_max_count    = 6
worker_min_count = 2
worker_max_count = 4

# ── ElastiCache ───────────────────────────────────────────────────────────────
# Upgrade to cache.r6g.large for load testing (more memory + higher connection
# limit). WARNING: changing node_type replaces the Redis instance — data loss.
elasticache_node_type = "cache.t3.micro"
