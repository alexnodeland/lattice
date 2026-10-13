# The state-host module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_subnet" {
    defaults = { availability_zone = "us-east-1a" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mocked" }
  }
  mock_resource "aws_ebs_volume" {
    defaults = { id = "vol-0123456789abcdef0" }
  }
}

variables {
  name                                 = "stackr"
  subnet_id                            = "subnet-a"
  private_ip                           = "10.40.128.10"
  vpc_id                               = "vpc-mocked"
  services_security_group_id           = "sg-services"
  namespace_id                         = "ns-mocked"
  clickhouse_password_secret_arn       = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-AbCdEf"
  clickhouse_admin_password_secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-admin-AbCdEf"
  lattice_ref                          = "stackr-v0.1.0"
}

run "state_host_imdsv2_encrypted_disks_and_daily_snapshots" {
  command = plan
  module {
    source = "./modules/state-host"
  }

  assert {
    condition     = aws_instance.this.metadata_options[0].http_tokens == "required"
    error_message = "The instance answers IMDSv2 only."
  }
  assert {
    condition     = aws_ebs_volume.data.encrypted && aws_instance.this.root_block_device[0].encrypted
    error_message = "Both disks are encrypted."
  }
  assert {
    condition     = aws_dlm_lifecycle_policy.this.policy_details[0].schedule[0].retain_rule[0].count == 14
    error_message = "DLM keeps 14 daily snapshots by default."
  }
}

run "state_host_takes_only_the_services_and_reaches_out_only_over_http_and_https" {
  command = plan
  module {
    source = "./modules/state-host"
  }

  assert {
    condition = alltrue([
      for rule in aws_vpc_security_group_ingress_rule.this :
      rule.referenced_security_group_id == "sg-services" && rule.cidr_ipv4 == null && contains([8123, 9000, 9090, 9091], rule.from_port)
    ])
    error_message = "The state host takes ClickHouse's, Prometheus's and prom-label-proxy's ports from the services only."
  }
  assert {
    condition     = toset([for rule in aws_vpc_security_group_egress_rule.this : rule.from_port]) == toset([80, 443])
    error_message = "The state host reaches out over HTTP and HTTPS only."
  }
  assert {
    condition = toset(jsondecode(aws_iam_role_policy.secret.policy).Statement[0].Resource) == toset([
      "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-AbCdEf",
      "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-admin-AbCdEf",
    ])
    error_message = "The state host may read ClickHouse's two passwords, and no other secret."
  }
}

run "state_host_names_its_three_services_at_its_fixed_address" {
  command = plan
  module {
    source = "./modules/state-host"
  }

  assert {
    condition     = toset(keys(aws_service_discovery_instance.this)) == toset(["clickhouse", "prometheus", "prom-label-proxy"])
    error_message = "ClickHouse, Prometheus and prom-label-proxy are each named."
  }
  assert {
    condition     = alltrue([for instance in aws_service_discovery_instance.this : instance.attributes.AWS_INSTANCE_IPV4 == "10.40.128.10"])
    error_message = "Each name is the state host's fixed address."
  }
  assert {
    condition     = strcontains(aws_instance.this.user_data, "nvme-Amazon_Elastic_Block_Store_vol0123456789abcdef0") && strcontains(aws_instance.this.user_data, "--branch 'stackr-v0.1.0'")
    error_message = "The user data mounts the data volume by its id, and checks out the tag it was given."
  }
}
