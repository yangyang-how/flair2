variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet IDs for the ElastiCache subnet group"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs to attach to the ElastiCache cluster"
  type        = list(string)
}

variable "node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}
