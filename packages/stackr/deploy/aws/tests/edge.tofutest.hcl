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
  name              = "stackr"
  domain            = "example.com"
  zone_id           = "Z0000000000000"
  vpc_id            = "vpc-mocked"
  subnet_ids        = ["subnet-a", "subnet-b"]
  security_group_id = "sg-alb"
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
      && aws_lb_listener_rule.auth_admin.priority < aws_lb_listener_rule.host["auth"].priority
    )
    error_message = "GoTrue's admin API is refused before its host is forwarded."
  }
  assert {
    condition     = aws_lb_target_group.this["app"].port == 8000 && aws_lb_target_group.this["auth"].port == 9999
    error_message = "The application on 8000, GoTrue on 9999."
  }
}

run "edge_refuses_a_domain_that_isnt_one" {
  command = plan
  module {
    source = "./modules/edge"
  }
  variables {
    domain = "Example.com/x"
  }
  expect_failures = [var.domain]
}
