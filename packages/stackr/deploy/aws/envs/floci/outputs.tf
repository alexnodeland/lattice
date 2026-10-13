output "hosts" {
  description = "The names tier 2's smoke sends in its Host header."
  value       = module.stack.hosts
}

output "alb_dns_name" {
  description = "The ALB, which Floci serves plain HTTP on, on 443 (ADR-0025)."
  value       = module.stack.alb_dns_name
}
