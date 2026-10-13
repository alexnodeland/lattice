# The state-host module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
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
  # An instance given no key gets the mock's: one given a key would plan with that key's name.
  mock_resource "aws_instance" {
    defaults = { key_name = "" }
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
  namespace_id                         = "ns-mocked"
  clickhouse_password_secret_arn       = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-AbCdEf"
  clickhouse_admin_password_secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-admin-AbCdEf"
  lattice_commit                       = "0123456789abcdef0123456789abcdef01234567"
  ami_id                               = "ami-0123456789abcdef0"
}

run "state_host_imdsv2_encrypted_disks_and_daily_snapshots" {
  command = plan
  module {
    source = "./modules/state-host"
  }

  assert {
    condition     = aws_instance.this.metadata_options[0].http_tokens == "required" && aws_instance.this.metadata_options[0].http_put_response_hop_limit == 1
    error_message = "The instance answers IMDSv2 only, one hop away: never its services' containers."
  }
  assert {
    condition     = aws_instance.this.key_name == "" && aws_instance.this.ami == "ami-0123456789abcdef0"
    error_message = "No SSH key; and the AMI it is given, never a lookup that moves."
  }
  assert {
    condition     = aws_ebs_volume.data.final_snapshot && aws_volume_attachment.data.stop_instance_before_detaching
    error_message = "The data volume is snapshotted before a destroy, and the instance stops before it detaches."
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

run "state_host_reaches_out_only_over_http_and_https" {
  command = plan
  module {
    source = "./modules/state-host"
  }

  assert {
    condition = (
      toset([for rule in aws_vpc_security_group_egress_rule.this : rule.from_port]) == toset([80, 443])
      && alltrue([for rule in aws_vpc_security_group_egress_rule.this : rule.cidr_ipv4 == "0.0.0.0/0" && rule.to_port == rule.from_port])
    )
    error_message = "The state host reaches out over HTTP and HTTPS only."
  }
  assert {
    condition = (
      jsondecode(aws_iam_role_policy.session_manager.policy).Statement[0].Action == "ssm:UpdateInstanceInformation"
      && jsondecode(aws_iam_role_policy.session_manager.policy).Statement[0].Resource == "arn:aws:ec2:us-east-1:000000000000:instance/*"
      && alltrue([for action in jsondecode(aws_iam_role_policy.session_manager.policy).Statement[1].Action : can(regex("^(ssmmessages|ec2messages):", action))])
      && length(jsondecode(aws_iam_role_policy.session_manager.policy).Statement) == 2
    )
    error_message = "SSM's agent may run sessions, and read nothing of SSM's, such as its parameters."
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
    condition     = aws_ec2_subnet_cidr_reservation.this.cidr_block == "10.40.128.10/32" && aws_ec2_subnet_cidr_reservation.this.reservation_type == "explicit"
    error_message = "The fixed address is reserved in its subnet, so no task takes it."
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
    condition = (
      strcontains(aws_instance.this.user_data, "nvme-Amazon_Elastic_Block_Store_vol0123456789abcdef0")
      && strcontains(aws_instance.this.user_data, "fetch --quiet --depth 1 https://github.com/alexnodeland/lattice '0123456789abcdef0123456789abcdef01234567'")
    )
    error_message = "The user data mounts the data volume by its id, and checks out the commit it was given."
  }
  assert {
    condition = (
      strcontains(aws_instance.this.user_data, "docker run --rm --network host")
      && strcontains(aws_instance.this.user_data, "ExecStartPre=/usr/local/sbin/stackr-state-env")
      && strcontains(aws_instance.this.user_data, "--env-file /run/stackr/.env up")
      && strcontains(aws_instance.this.user_data, "--env-file /run/stackr/.env down")
    )
    error_message = "Each start reads the passwords afresh, on the host's network, into /run/stackr, which Compose reads."
  }
}

run "state_host_refuses_a_tag_for_a_commit_and_a_secrets_json_key" {
  command = plan
  module {
    source = "./modules/state-host"
  }
  variables {
    lattice_commit                 = "stackr-v0.1.0"
    clickhouse_password_secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-AbCdEf:password::"
  }
  expect_failures = [var.lattice_commit, var.clickhouse_password_secret_arn]
}
