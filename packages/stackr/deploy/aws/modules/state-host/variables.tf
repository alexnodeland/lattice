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

variable "services_security_group_id" {
  description = "The services' security group: the only one the state host takes traffic from."
  type        = string
}

variable "namespace_id" {
  description = "The private DNS namespace its three services are named in."
  type        = string
}

variable "clickhouse_password_secret_arn" {
  description = "The secret holding ClickHouse's password for Langfuse, which the instance reads at boot."
  type        = string
}

variable "clickhouse_admin_password_secret_arn" {
  description = "The secret holding ClickHouse's admin password, for operators, which the instance reads at boot."
  type        = string
}

variable "lattice_ref" {
  description = "The tag of lattice the instance checks out: deploy/aws/state-host is its Compose."
  type        = string
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

variable "ami_parameter" {
  description = "The SSM parameter that names the AMI: Ubuntu 24.04, arm64, which comes with the SSM agent."
  type        = string
  default     = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}

variable "aws_cli_image" {
  description = "The AWS CLI's image, pinned, which the user data reads the secret with."
  type        = string
  default     = "amazon/aws-cli:2.37.13@sha256:d32864c20087d486f5988c3e70817d67a73f584a47535cada9ad97e0ea1e5196"
}
