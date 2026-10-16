variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "subnet_id" {
  description = "The private subnet the instance and its volume live in: one zone."
  type        = string
}

variable "private_ip" {
  description = "The instance's fixed private address, which survives replacing it."
  type        = string
}

variable "vpc_id" {
  description = "The VPC the state host's security group is in."
  type        = string
}

variable "namespace_id" {
  description = "The private DNS namespace its three services are named in."
  type        = string
}

variable "clickhouse_password_secret_arn" {
  description = "The secret holding ClickHouse's password for Langfuse, which the instance reads each time it starts its services."
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:[^:]+$", var.clickhouse_password_secret_arn))
    error_message = "A whole secret's ARN: the instance reads it whole, without a JSON key."
  }
}

variable "clickhouse_admin_password_secret_arn" {
  description = "The secret holding ClickHouse's admin password, for operators, which the instance reads each time it starts its services."
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:[^:]+$", var.clickhouse_admin_password_secret_arn))
    error_message = "A whole secret's ARN: the instance reads it whole, without a JSON key."
  }
}

variable "clickhouse_backup_password_secret_arn" {
  description = "The secret holding the password of ClickHouse's `backup` user, which the instance reads each time it starts its services."
  type        = string

  validation {
    condition     = can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:[^:]+$", var.clickhouse_backup_password_secret_arn))
    error_message = "A whole secret's ARN: the instance reads it whole, without a JSON key."
  }
}

variable "backups_bucket" {
  description = "The backups bucket (data's), whose clickhouse/ and drill/ prefixes the instance's role may write and read: ClickHouse's backups and the restore drill's (ADR-0037)."
  type        = object({ name = string, arn = string })

  validation {
    condition     = can(regex("^arn:[^:]+:s3:::[^/]+$", var.backups_bucket.arn))
    error_message = "A bucket's ARN, not an object's."
  }
}

variable "lattice_commit" {
  description = "The commit of lattice the instance checks out, by its full SHA, which can't move as a tag can: deploy/aws/state-host is its Compose."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{40}$", var.lattice_commit))
    error_message = "A commit's full SHA: 40 lowercase hexadecimal digits."
  }
}

variable "instance_type" {
  description = "The instance's type: Graviton, as the AMI is arm64."
  type        = string
  default     = "t4g.large"
}

variable "volume_size" {
  description = "The data volume's size, in GiB: ClickHouse's and Prometheus's data."
  type        = number
  default     = 100
}

variable "snapshot_retention" {
  description = "How many of the data volume's daily snapshots DLM keeps."
  type        = number
  default     = 14

  validation {
    condition     = var.snapshot_retention >= 1 && var.snapshot_retention <= 1000
    error_message = "DLM keeps 1 to 1000 snapshots."
  }
}

variable "ami_id" {
  description = <<-EOT
    The AMI: Ubuntu 24.04, arm64, which comes with the SSM agent, in the deployment's region. It is
    pinned, since a new AMI replaces the instance: bump it on purpose, to the ID that SSM's
    /aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id names.
  EOT
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]{8}([0-9a-f]{9})?$", var.ami_id))
    error_message = "An AMI's ID: ami- and 8 or 17 hexadecimal digits."
  }
}

variable "final_snapshot" {
  description = "Whether destroying the data volume snapshots it first: off only where nothing is kept."
  type        = bool
  default     = true
}

variable "aws_cli_image" {
  description = "The AWS CLI's image, pinned, which the user data reads the secret with."
  type        = string
  default     = "amazon/aws-cli:2.37.13@sha256:d32864c20087d486f5988c3e70817d67a73f584a47535cada9ad97e0ea1e5196"
}
