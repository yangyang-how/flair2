variable "project" {
  description = "Project name — used as a prefix for all resource names"
  type        = string
  default     = "flair2"
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod"
  }
}

variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-west-2"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ) — used by ALB"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ) — used by ECS and ElastiCache"
  type        = list(string)
  default     = ["10.0.11.0/24", "10.0.12.0/24"]
}

variable "availability_zones" {
  description = "AZs to spread subnets across (must match subnet CIDR count)"
  type        = list(string)
  default     = ["us-west-2a", "us-west-2b"]
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for the ALB HTTPS listener (provision manually in AWS Console)"
  type        = string
}
