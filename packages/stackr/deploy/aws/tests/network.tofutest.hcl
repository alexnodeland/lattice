# The network module, planned against a mocked AWS (tier 1, RFC-0004). Mocked values are random,
# and the provider checks some shapes even then: a policy's JSON, and an ARN where another
# resource takes one.

mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\": \"2012-10-17\", \"Statement\": []}" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:000000000000:log-group:mocked" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mocked" }
  }
}

variables {
  name  = "stackr"
  zones = ["us-east-1a", "us-east-1b"]
}

run "network_a_public_and_a_private_subnet_in_each_zone" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2
    error_message = "Each zone needs a public and a private subnet."
  }
  assert {
    condition     = toset([for subnet in aws_subnet.private : subnet.cidr_block]) == toset(["10.40.128.0/20", "10.40.144.0/20"])
    error_message = "The private subnets are the VPC's upper half."
  }
}

run "network_only_the_alb_is_reachable_from_anywhere" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.alb : contains([80, 443], rule.from_port)
    ])
    error_message = "The ALB takes only 80 and 443 from anywhere."
  }
  assert {
    condition = alltrue(concat(
      [for rule in aws_vpc_security_group_ingress_rule.services : rule.cidr_ipv4 == null],
      [for rule in aws_vpc_security_group_ingress_rule.data : rule.cidr_ipv4 == null],
    ))
    error_message = "The services and the data stores take traffic from security groups, never from an address range."
  }
}

run "network_two_zones_and_no_other_number" {
  command = plan
  module {
    source = "./modules/network"
  }

  variables {
    zones = ["us-east-1a"]
  }
  expect_failures = [var.zones]
}
