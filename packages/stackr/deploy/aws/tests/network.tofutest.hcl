# The network module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
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

run "network_a_public_and_a_private_subnet_in_each_zone_none_giving_addresses" {
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
  assert {
    condition     = alltrue([for subnet in concat(values(aws_subnet.public), values(aws_subnet.private)) : !subnet.map_public_ip_on_launch])
    error_message = "No subnet gives what launches in it a public address."
  }
  assert {
    condition     = length(aws_default_security_group.this.ingress) == 0 && length(aws_default_security_group.this.egress) == 0
    error_message = "The VPC's default security group lets nothing in or out."
  }
}

run "network_only_the_alb_takes_traffic_from_anywhere_and_only_on_80_and_443" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition     = toset([for rule in aws_vpc_security_group_ingress_rule.alb : rule.from_port]) == toset([80, 443]) && alltrue([for rule in aws_vpc_security_group_ingress_rule.alb : rule.from_port == rule.to_port])
    error_message = "The ALB takes 80 and 443 from anywhere, and nothing else."
  }
}

run "network_tasks_reach_out_over_https_only" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition     = aws_vpc_security_group_egress_rule.tasks_https.from_port == 443 && aws_vpc_security_group_egress_rule.tasks_https.to_port == 443
    error_message = "Every task reaches out over HTTPS only; who reaches whom inside is the stack's."
  }
  assert {
    condition     = length(aws_security_group.tasks.ingress) == 0
    error_message = "The group every task shares lets nothing in."
  }
}

run "network_flow_logs_everything_with_a_role_only_this_account_may_use" {
  command = plan
  module {
    source = "./modules/network"
  }

  assert {
    condition     = aws_flow_log.this.traffic_type == "ALL"
    error_message = "Flow logs record accepted and rejected traffic."
  }
  assert {
    condition     = jsondecode(aws_iam_role.flow.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "000000000000"
    error_message = "The flow logs' role trusts this account's flow logs only."
  }
}

run "network_refuses_one_zone" {
  command = plan
  module {
    source = "./modules/network"
  }
  variables {
    zones = ["us-east-1a"]
  }
  expect_failures = [var.zones]
}

run "network_refuses_a_range_that_isnt_a_16" {
  command = plan
  module {
    source = "./modules/network"
  }
  variables {
    cidr = "10.40.0.0/20"
  }
  expect_failures = [var.cidr]
}

run "network_refuses_a_name_that_isnt_one" {
  command = plan
  module {
    source = "./modules/network"
  }
  variables {
    name = "Stackr_Prod"
  }
  expect_failures = [var.name]
}
