variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "env" {
  description = "Deployment environment: dev or prod"
  type        = string
}

variable "account_id" {
  description = "AWS account ID — used to scope IAM policy resource ARNs"
  type        = string
}
