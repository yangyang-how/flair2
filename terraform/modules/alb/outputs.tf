output "dns_name" {
  description = "ALB DNS name — set as CNAME target in Cloudflare"
  value       = aws_lb.main.dns_name
}

output "target_group_arn" {
  description = "ARN of the API target group (passed to ECS service)"
  value       = aws_lb_target_group.api.arn
}

output "alb_arn" {
  description = "ARN of the ALB"
  value       = aws_lb.main.arn
}
