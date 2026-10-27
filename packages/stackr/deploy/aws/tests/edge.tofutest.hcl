# The edge module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/mocked"
      domain_validation_options = [
        { domain_name = "app.example.com", resource_record_name = "_a.app.example.com.", resource_record_type = "CNAME", resource_record_value = "_a.acm-validations.aws." },
        { domain_name = "auth.example.com", resource_record_name = "_a.auth.example.com.", resource_record_type = "CNAME", resource_record_value = "_b.acm-validations.aws." },
      ]
    }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/stackr/mocked" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/stackr/mocked/mocked" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/stackr/mocked" }
  }
}

variables {
  name                = "stackr"
  domain              = "example.com"
  zone_id             = "Z0000000000000"
  vpc_id              = "vpc-mocked"
  subnet_ids          = ["subnet-a", "subnet-b"]
  public_subnet_cidrs = ["10.40.0.0/20", "10.40.16.0/20"]
  security_group_id   = "sg-alb"
  access_logs         = { bucket = "stackr-access-logs-mocked", prefix = "alb" }
}

run "edge_http_only_redirects_and_https_uses_tls_1_3" {
  command = plan
  module {
    source = "./modules/edge"
  }

  assert {
    condition     = aws_lb_listener.http.default_action[0].type == "redirect" && aws_lb_listener.http.default_action[0].redirect[0].protocol == "HTTPS"
    error_message = "Port 80 only redirects to HTTPS."
  }
  assert {
    condition     = aws_lb_listener.https.ssl_policy == "ELBSecurityPolicy-TLS13-1-2-2021-06"
    error_message = "HTTPS offers TLS 1.3 and 1.2 only."
  }
  assert {
    condition     = aws_lb.this.drop_invalid_header_fields && aws_lb.this.enable_deletion_protection
    error_message = "The ALB drops invalid headers, and refuses to be deleted by default."
  }
  assert {
    condition = (
      aws_lb_listener.https.routing_http_response_strict_transport_security_header_value == "max-age=31536000; includeSubDomains"
      && aws_lb_listener.https.routing_http_response_x_content_type_options_header_value == "nosniff"
      && aws_lb_listener.https.routing_http_response_server_enabled == false
    )
    error_message = "HTTPS sends the single host's headers: HSTS and nosniff, and no Server."
  }
  assert {
    condition     = aws_lb.this.access_logs[0].enabled && aws_lb.this.access_logs[0].bucket == "stackr-access-logs-mocked" && aws_lb.this.access_logs[0].prefix == "alb"
    error_message = "The ALB writes its access logs to the bucket it is given, under its prefix."
  }
  assert {
    condition     = alltrue([for record in aws_route53_record.validation : record.allow_overwrite])
    error_message = "The certificate's validation records take over records left from an earlier certificate."
  }
}

run "edge_routes_each_host_and_refuses_gotrues_admin_api_first" {
  command = plan
  module {
    source = "./modules/edge"
  }

  assert {
    condition     = output.hosts == { app = "app.example.com", auth = "auth.example.com" }
    error_message = "The application at app.<domain>, GoTrue at auth.<domain>."
  }
  assert {
    condition = (
      aws_lb_listener_rule.auth_admin.action[0].fixed_response[0].status_code == "404"
      && aws_lb_listener_rule.auth_admin.priority < aws_lb_listener_rule.auth.priority
      && toset(flatten([for condition in aws_lb_listener_rule.auth_admin.condition : [for host in condition.host_header : host.values]])) == toset(["auth.example.com"])
      && toset(flatten([for condition in aws_lb_listener_rule.auth_admin.condition : [for path in condition.path_pattern : path.values]])) == toset(["/admin", "/admin/*"])
    )
    error_message = "GoTrue's admin API, /admin and below on auth.<domain>, is refused before its host is forwarded."
  }
  assert {
    condition     = aws_lb_listener.https.default_action[0].type == "fixed-response" && aws_lb_listener.https.default_action[0].fixed_response[0].status_code == "404"
    error_message = "HTTPS answers 404 to any other host."
  }
  assert {
    condition     = aws_lb_target_group.this["app"].port == 8000 && aws_lb_target_group.this["auth"].port == 9999
    error_message = "The application on 8000, GoTrue on 9999."
  }
}

run "edge_gives_gotrue_a_proxy_that_trusts_only_the_albs_subnets" {
  command = plan
  module {
    source = "./modules/edge"
  }

  assert {
    condition = (
      strcontains(output.auth_proxy.caddyfile, "trusted_proxies static 10.40.0.0/20 10.40.16.0/20\n")
      && strcontains(output.auth_proxy.caddyfile, "trusted_proxies_strict")
      && strcontains(output.auth_proxy.caddyfile, "client_ip_headers X-Forwarded-For")
    )
    error_message = "GoTrue's proxy takes X-Forwarded-For from the ALB's subnets only, and its right-most address it doesn't trust."
  }
  assert {
    condition = (
      strcontains(output.auth_proxy.caddyfile, ":9999 {")
      && strcontains(output.auth_proxy.caddyfile, "reverse_proxy 127.0.0.1:9998 {")
      && strcontains(output.auth_proxy.caddyfile, "header_up X-Forwarded-For {client_ip}")
      && output.auth_proxy.gotrue_port == 9998
    )
    error_message = "The proxy takes GoTrue's port, and passes GoTrue, on the task's loopback, the one address it found."
  }
  assert {
    condition     = startswith(output.auth_proxy.image, "caddy:") && strcontains(output.auth_proxy.image, "@sha256:")
    error_message = "The proxy is Caddy, pinned by digest."
  }
}

run "edge_refuses_a_domain_that_isnt_one" {
  command = plan
  module {
    source = "./modules/edge"
  }
  variables {
    domain = "example..com"
  }
  expect_failures = [var.domain]
}
