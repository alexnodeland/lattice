# The state host (RFC-0004, stackr ADR-0025): one EC2 instance that runs ClickHouse, Prometheus and
# prom-label-proxy with Compose under systemd, from deploy/aws/state-host in a checkout of lattice,
# with their data on an EBS volume of its own that DLM snapshots daily. Its address is fixed, and
# named in the private namespace. Operators reach the admin UIs through it with SSM port
# forwarding: it opens no port for that, and has no SSH key.

data "aws_subnet" "this" {
  id = var.subnet_id
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

resource "aws_iam_role" "this" {
  name = "${var.name}-state-host"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

# SSM's agent: Session Manager and port forwarding, without SSH, and nothing else of SSM's, such as
# its parameters. It registers as an instance of this account's; its channels' and messages'
# actions can't be narrowed to a resource.
resource "aws_iam_role_policy" "session_manager" {
  role = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "ssm:UpdateInstanceInformation"
        Resource = "arn:${data.aws_partition.current.partition}:ec2:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:instance/*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
          "ec2messages:AcknowledgeMessage",
          "ec2messages:DeleteMessage",
          "ec2messages:FailMessage",
          "ec2messages:GetEndpoint",
          "ec2messages:GetMessages",
          "ec2messages:SendReply",
        ]
        Resource = "*"
      },
    ]
  })
}

# Its two secrets: ClickHouse's passwords, Langfuse's and the admin's.
resource "aws_iam_role_policy" "secret" {
  role = aws_iam_role.this.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "secretsmanager:GetSecretValue"
      Resource = [var.clickhouse_password_secret_arn, var.clickhouse_admin_password_secret_arn]
    }]
  })
}

resource "aws_iam_instance_profile" "this" {
  name = "${var.name}-state-host"
  role = aws_iam_role.this.name
}

# Its address, kept from the subnet's own assignments, so no task takes it while the instance is
# being replaced.
resource "aws_ec2_subnet_cidr_reservation" "this" {
  subnet_id        = var.subnet_id
  cidr_block       = "${var.private_ip}/32"
  reservation_type = "explicit"
  description      = "${var.name} state host"
}

resource "aws_network_interface" "this" {
  subnet_id       = var.subnet_id
  private_ips     = [var.private_ip]
  security_groups = [aws_security_group.this.id]
  tags            = { Name = "${var.name}-state-host" }
  depends_on      = [aws_ec2_subnet_cidr_reservation.this]
}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.this.availability_zone
  size              = var.volume_size
  type              = "gp3"
  encrypted         = true
  # A destroy, or a move to another zone, snapshots it first.
  final_snapshot = var.final_snapshot
  tags           = { Name = "${var.name}-state", Snapshot = "${var.name}-state" }
}

resource "aws_instance" "this" {
  ami                  = var.ami_id
  instance_type        = var.instance_type
  iam_instance_profile = aws_iam_instance_profile.this.name
  ebs_optimized        = true
  monitoring           = true

  primary_network_interface {
    network_interface_id = aws_network_interface.this.id
  }

  # IMDSv2 only, one hop: the AWS CLI reads the secrets on the host's network, and the services'
  # containers, on Compose's, can't reach it.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    encrypted   = true
    volume_type = "gp3"
    volume_size = 30
  }

  user_data_replace_on_change = true
  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    volume_id      = aws_ebs_volume.data.id
    address        = var.private_ip
    lattice_commit = var.lattice_commit
    secret_arn     = var.clickhouse_password_secret_arn
    admin_arn      = var.clickhouse_admin_password_secret_arn
    region         = data.aws_region.current.region
    aws_cli_image  = var.aws_cli_image
  })

  tags = { Name = "${var.name}-state-host" }
}

# Replacing the instance stops it first, so the volume is unmounted cleanly before it detaches.
resource "aws_volume_attachment" "data" {
  device_name                    = "/dev/sdf"
  volume_id                      = aws_ebs_volume.data.id
  instance_id                    = aws_instance.this.id
  stop_instance_before_detaching = true
}

# The data volume's daily snapshots.
resource "aws_iam_role" "dlm" {
  name = "${var.name}-state-snapshots"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "dlm.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "dlm" {
  role       = aws_iam_role.dlm.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole"
}

resource "aws_dlm_lifecycle_policy" "this" {
  # Letters, digits, spaces, hyphens and underscores only.
  description        = "${var.name} state host data volume daily"
  execution_role_arn = aws_iam_role.dlm.arn
  state              = "ENABLED"

  policy_details {
    resource_types = ["VOLUME"]
    target_tags    = { Snapshot = "${var.name}-state" }

    schedule {
      name      = "daily"
      copy_tags = true
      create_rule {
        interval      = 24
        interval_unit = "HOURS"
        times         = ["03:00"]
      }
      retain_rule {
        count = var.snapshot_retention
      }
    }
  }
}

# Its three services, by name in the private namespace, at its fixed address.
resource "aws_service_discovery_service" "this" {
  for_each = toset(["clickhouse", "prometheus", "prom-label-proxy"])
  name     = each.key

  dns_config {
    namespace_id = var.namespace_id
    dns_records {
      ttl  = 60
      type = "A"
    }
  }
}

resource "aws_service_discovery_instance" "this" {
  for_each    = aws_service_discovery_service.this
  instance_id = "${var.name}-state-host"
  service_id  = each.value.id
  attributes = {
    AWS_INSTANCE_IPV4 = var.private_ip
  }
}
