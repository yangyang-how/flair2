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
  description = "Lambda function timeout in seconds — issue #28 specifies 15 min max (Lambda ceiling is 900s)"
  type        = number
  default     = 900
}

variable "memory_size" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "enable_lambda" {
  description = "Set to true to create the Lambda function. Default false so CI plan/validate succeeds without a local zip artifact."
  type        = bool
  default     = false
}
