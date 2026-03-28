locals {
  prefix = "${var.project}-${var.env}"
}

# ── pipeline_runs table ───────────────────────────────────────────────────────
# Stores PipelineRun records: status, config, stage progress, S3 results key
# Partition key: run_id (UUID)

resource "aws_dynamodb_table" "pipeline_runs" {
  name         = "${local.prefix}-pipeline-runs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  # GSI on session_id so the frontend can list all runs for a session
  attribute {
    name = "session_id"
    type = "S"
  }

  global_secondary_index {
    name            = "session_id-index"
    hash_key        = "session_id"
    projection_type = "ALL"
  }

  # Auto-expire runs after 7 days (TTL attribute set by app code)
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = { Name = "${local.prefix}-pipeline-runs" }
}

# ── video_performance table ───────────────────────────────────────────────────
# Stores VideoPerformance records: views, likes, completion_rate, committee_rank
# Partition key: run_id, Sort key: script_id

resource "aws_dynamodb_table" "video_performance" {
  name         = "${local.prefix}-video-performance"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "run_id"
  range_key    = "script_id"

  attribute {
    name = "run_id"
    type = "S"
  }

  attribute {
    name = "script_id"
    type = "S"
  }

  tags = { Name = "${local.prefix}-video-performance" }
}
