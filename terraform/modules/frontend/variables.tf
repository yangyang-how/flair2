variable "project" {
  description = "Project name prefix"
  type        = string
}

variable "env" {
  description = "Deployment environment"
  type        = string
}

variable "api_origin" {
  description = "Backend ALB DNS name (for CORS and API proxy)"
  type        = string
}
