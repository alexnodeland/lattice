output "target_groups" {
  description = "The target groups, app and auth, that the application's and GoTrue's services register with."
  value       = { for key, group in aws_lb_target_group.this : key => group.arn }
  # ECS refuses a service whose target group no listener forwards to yet.
  depends_on = [aws_lb_listener_rule.app, aws_lb_listener_rule.auth]
}

output "hosts" {
  description = "The names users reach: app.<domain> and auth.<domain>."
  value       = { for key, host in local.hosts : key => host.name }
}

output "auth_proxy" {
  description = <<-EOT
    GoTrue's proxy, for its task: Caddy's image, and its configuration, which trusts only the ALB's
    subnets for X-Forwarded-For and passes GoTrue the one address it found. GoTrue listens on the
    task's loopback at `gotrue_port`.
  EOT
  value = {
    image = var.caddy_image
    caddyfile = templatefile("${path.module}/auth-proxy.Caddyfile.tftpl", {
      port            = local.hosts.auth.port
      gotrue_port     = local.gotrue_port
      trusted_proxies = join(" ", var.public_subnet_cidrs)
    })
    gotrue_port = local.gotrue_port
  }
}

output "alb_dns_name" {
  description = "The ALB's own name, which Route 53's records alias."
  value       = aws_lb.this.dns_name
}
