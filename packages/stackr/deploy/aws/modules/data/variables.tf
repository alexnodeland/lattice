variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string
}

variable "subnet_ids" {
  description = "The private subnets RDS and ElastiCache live in."
  type        = list(string)
}

variable "security_group_id" {
  description = "The data stores' security group, which lets in only the services."
  type        = string
}

variable "postgres" {
  description = "RDS for PostgreSQL: its size, and what a destroy may do to it."
  type = object({
    instance_class        = optional(string, "db.t4g.medium")
    allocated_storage     = optional(number, 50)
    max_allocated_storage = optional(number, 200)
    backup_retention_days = optional(number, 14)
    deletion_protection   = optional(bool, true)
    skip_final_snapshot   = optional(bool, false)
  })
  default = {}
}

variable "valkey" {
  description = "ElastiCache for Valkey: its size and port, and its auth token's version."
  type = object({
    node_type             = optional(string, "cache.t4g.small")
    port                  = optional(number, 6379)
    snapshot_retention    = optional(number, 7)
    auth_token_wo_version = optional(number, 1)
  })
  default = {}
}

variable "valkey_auth_token" {
  description = "Valkey's auth token, read from its secret by the caller: never in state."
  type        = string
  ephemeral   = true
  sensitive   = true
}

variable "buckets" {
  description = "The S3 buckets, by role (langfuse, telemetry, backups), each named <name>-<role>."
  type        = set(string)
  default     = ["langfuse", "telemetry", "backups"]
}

variable "force_destroy_buckets" {
  description = "Whether a destroy empties the buckets first: only where nothing is kept."
  type        = bool
  default     = false
}
