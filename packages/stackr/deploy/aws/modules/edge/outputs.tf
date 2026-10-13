output "target_groups" {
  description = "The target groups, app and auth, that the application's and GoTrue's services register with."
  value       = { for key, group in aws_lb_target_group.this : key => group.arn }
}

output "hosts" {
  description = "The names users reach: app.<domain> and auth.<domain>."
  value       = local.hosts
}

output "alb_dns_name" {
  description = "The ALB's own name, which Route 53's records alias."
  value       = aws_lb.this.dns_name
}
