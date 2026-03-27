variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
}

variable "execution_role_arn" {
  description = "IAM role ARN for the Lambda function"
  type        = string
}

variable "s3_bucket_name" {
  description = "S3 bucket name where generated videos will be stored"
  type        = string
}

variable "timeout" {
  description = "Lambda function timeout in seconds (video generation can take a while)"
  type        = number
  default     = 300
}

variable "memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}
