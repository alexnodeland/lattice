output "hosts" {
  description = "The names tier 2's smoke sends in its Host header."
  value       = module.stack.hosts
}

output "alb_dns_name" {
  description = "The ALB, which Floci serves plain HTTP on, on 443 (ADR-0025)."
  value       = module.stack.alb_dns_name
}

output "backups_bucket" {
  description = "The backups bucket, which tier 2 points a ClickHouse's backups at."
  value       = module.stack.backups_bucket
}

output "cluster_arn" {
  description = "The ECS cluster, whose services tier 2 waits for."
  value       = module.stack.cluster_arn
}
