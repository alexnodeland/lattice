# The edge (RFC-0004): an ALB with an ACM certificate for app.<domain> and auth.<domain>, validated
# through Route 53. HTTP redirects to HTTPS; the application's host goes to its target group, and
# GoTrue's to its own, at its root, with its admin API refused at the edge, as on the single host.

locals {
  hosts = {
    app  = "app.${var.domain}"
    auth = "auth.${var.domain}"
  }
  # Each target group's port and health check: the template's app, and GoTrue.
  targets = {
    app  = { port = 8000, health = "/healthz" }
    auth = { port = 9999, health = "/health" }
  }
}

resource "aws_acm_certificate" "this" {
  domain_name               = local.hosts.app
  subject_alternative_names = [local.hosts.auth]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  for_each = {
    for option in aws_acm_certificate.this.domain_validation_options : option.domain_name => option
  }
  zone_id = var.zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 300
}

resource "aws_acm_certificate_validation" "this" {
  certificate_arn         = aws_acm_certificate.this.arn
  validation_record_fqdns = [for record in aws_route53_record.validation : record.fqdn]
}

resource "aws_lb" "this" {
  name                       = var.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.subnet_ids
  security_groups            = [var.security_group_id]
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
}

resource "aws_lb_target_group" "this" {
  for_each    = local.targets
  name        = "${var.name}-${each.key}"
  port        = each.value.port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id

  health_check {
    path    = each.value.health
    matcher = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.this.certificate_arn

  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not found"
      status_code  = "404"
    }
  }
}

# GoTrue's admin API is for the application's admin commands, on the private network.
resource "aws_lb_listener_rule" "auth_admin" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Not found"
      status_code  = "404"
    }
  }
  condition {
    host_header {
      values = [local.hosts.auth]
    }
  }
  condition {
    path_pattern {
      values = ["/admin", "/admin/*"]
    }
  }
}

resource "aws_lb_listener_rule" "host" {
  for_each     = local.hosts
  listener_arn = aws_lb_listener.https.arn
  priority     = each.key == "app" ? 20 : 30

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.this[each.key].arn
  }
  condition {
    host_header {
      values = [each.value]
    }
  }
}

resource "aws_route53_record" "host" {
  for_each = local.hosts
  zone_id  = var.zone_id
  name     = each.value
  type     = "A"

  alias {
    name                   = aws_lb.this.dns_name
    zone_id                = aws_lb.this.zone_id
    evaluate_target_health = true
  }
}
