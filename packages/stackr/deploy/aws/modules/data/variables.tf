variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "vpc_id" {
  description = "The VPC the data stores' security group is in."
  type        = string
}

variable "subnet_ids" {
  description = "The private subnets RDS and ElastiCache live in."
  type        = list(string)
}

variable "postgres" {
  description = "RDS for PostgreSQL: its size, its backups, and what a destroy may do to it."
  type = object({
    instance_class        = optional(string, "db.t4g.medium")
    allocated_storage     = optional(number, 50)
    max_allocated_storage = optional(number, 200)
    backup_retention_days = optional(number, 14)
    deletion_protection   = optional(bool, true)
    skip_final_snapshot   = optional(bool, false)
  })
  default = {}

  validation {
    condition     = var.postgres.backup_retention_days >= 1 && var.postgres.backup_retention_days <= 35
    error_message = "RDS keeps automated backups for 1 to 35 days: 0 would turn them off."
  }
}

variable "valkey" {
  description = <<-EOT
    ElastiCache for Valkey: its size, its port, and its auth token's version, which moves with
    the version of the token's secret: raising both writes a new token to each.
  EOT
  type = object({
    node_type             = optional(string, "cache.t4g.small")
    port                  = optional(number, 6379)
    snapshot_retention    = optional(number, 7)
    auth_token_wo_version = optional(number, 1)
  })
  default = {}

  validation {
    condition     = var.valkey.port >= 1024 && var.valkey.port <= 65535
    error_message = "Valkey's port is 1024 to 65535."
  }
}

variable "valkey_auth_token" {
  description = "Valkey's auth token, read from its secret by the caller: never in state."
  type        = string
  ephemeral   = true
  sensitive   = true

  validation {
    condition     = length(var.valkey_auth_token) >= 16 && length(var.valkey_auth_token) <= 128
    error_message = "ElastiCache takes an auth token of 16 to 128 characters."
  }
}

variable "buckets" {
  description = "The S3 buckets, by role (langfuse, telemetry, backups, access-logs), each named <name>-<role>-<unique suffix>."
  type        = set(string)
  default     = ["langfuse", "telemetry", "backups", "access-logs"]
}

variable "clickhouse_backup_retention_days" {
  description = <<-EOT
    How many days the state host's ClickHouse backups (clickhouse/ in the backups bucket) are kept,
    whole each night (ADR-0037): their size times this is what they cost, and each is kept 7 days
    more as a noncurrent version once expired. The restore drill's own backups (drill/) are kept 7
    days. At least 2, so that last night's backup is still there while tonight's is written.
  EOT
  type        = number
  default     = 14

  validation {
    condition     = var.clickhouse_backup_retention_days == floor(var.clickhouse_backup_retention_days) && var.clickhouse_backup_retention_days >= 2 && var.clickhouse_backup_retention_days <= 365
    error_message = "ClickHouse's backups are kept a whole number of days, 2 to 365: with fewer, last night's could expire before tonight's is written, and none would be left."
  }
}

variable "force_destroy_buckets" {
  description = "Whether a destroy empties the buckets first: only where nothing is kept."
  type        = bool
  default     = false
}
