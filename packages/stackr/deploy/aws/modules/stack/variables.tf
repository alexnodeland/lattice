variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "environment" {
  description = "The deployment's environment, which every service's telemetry is labelled with."
  type        = string
  default     = "production"
}

variable "domain" {
  description = "The domain users reach: the application at app.<domain>, GoTrue at auth.<domain>."
  type        = string
}

variable "zone_id" {
  description = "The domain's Route 53 hosted zone."
  type        = string
}

variable "zones" {
  description = "Two availability zones. The state host lives in the first."
  type        = list(string)
}

variable "cidr" {
  description = "The VPC's address range, a /16."
  type        = string
  default     = "10.40.0.0/16"
}

variable "state_host" {
  description = <<-EOT
    Where ClickHouse, Prometheus and prom-label-proxy run: `ec2`, the state host, with its volume;
    or `fargate`, three services without one, for Floci, which can't run the state host (ADR-0025).
  EOT
  type        = string
  default     = "ec2"

  validation {
    condition     = contains(["ec2", "fargate"], var.state_host)
    error_message = "The state host is ec2 or fargate."
  }
  validation {
    condition     = var.state_host == "ec2" || (var.destroyable && var.aws_endpoint_url != null)
    error_message = "The state host's services run on Fargate only on Floci: destroyable, with its aws_endpoint_url."
  }
}

variable "ami_id" {
  description = "The state host's AMI, pinned (the state-host module says how to bump it); none on Fargate."
  type        = string
  default     = null

  validation {
    condition     = var.state_host == "fargate" || var.ami_id != null
    error_message = "The state host on EC2 needs its AMI."
  }
}

variable "lattice_commit" {
  description = "The commit of lattice the state host checks out, by its full SHA; none on Fargate."
  type        = string
  default     = null

  validation {
    condition     = var.state_host == "fargate" || var.lattice_commit != null
    error_message = "The state host on EC2 needs lattice's commit."
  }
}

variable "images" {
  description = "stackr's thin images, each by digest: the upstream image with stackr's configuration in it (RFC-0004)."
  type = object({
    otel_collector = string
    tempo          = string
    loki           = string
    pyroscope      = string
    grafana        = string
    litellm        = string
    db_init        = string
    auth_keys      = string
  })
}

variable "application" {
  description = <<-EOT
    The application generated from stackr's template: its name (project_slug), its image by
    digest, its access (`grantr`, with row-level security's two roles and db-roles, or `none`),
    and its own settings and secrets (ARNs), beside those the stack gives it.
  EOT
  type = object({
    name        = string
    image       = string
    access      = optional(string, "grantr")
    environment = optional(map(string), {})
    secrets     = optional(map(string), {})
  })

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.application.name))
    error_message = "The application's name is its project_slug: lowercase letters, digits and hyphens."
  }
  validation {
    condition     = !contains(["postgres", "grafana", "langfuse", "litellm", "gotrue", "auth", "rdsadmin"], replace(var.application.name, "-", "_")) && !startswith(replace(var.application.name, "-", "_"), "rds_")
    error_message = "The application's database and role are named after it, so it can't share a name with the stack's own, or RDS's (rdsadmin, rds_*)."
  }
  validation {
    condition     = can(regex("^[a-z_][a-z0-9_]{0,62}$", lookup(var.application.environment, "DATABASE_SCHEMA", "public")))
    error_message = "The application's DATABASE_SCHEMA is a plain lowercase identifier, as the template's settings take it."
  }
  validation {
    condition     = contains(["grantr", "none"], var.application.access)
    error_message = "The application's access is grantr or none."
  }
}

variable "sizes" {
  description = "Each service's CPU units and memory (MiB), by its name, over the defaults in locals.tf."
  type = map(object({
    cpu    = number
    memory = number
  }))
  default = {}
}

variable "postgres" {
  description = "RDS for PostgreSQL's size and backups, as the data module takes them."
  type = object({
    instance_class        = optional(string, "db.t4g.medium")
    allocated_storage     = optional(number, 50)
    max_allocated_storage = optional(number, 200)
    backup_retention_days = optional(number, 14)
  })
  default = {}
}

variable "valkey" {
  description = "ElastiCache for Valkey's size and port, as the data module takes them."
  type = object({
    node_type          = optional(string, "cache.t4g.small")
    port               = optional(number, 6379)
    snapshot_retention = optional(number, 7)
  })
  default = {}
}

variable "state_host_instance_type" {
  description = "The state host's instance type."
  type        = string
  default     = "t4g.large"
}

variable "clickhouse_backup_retention_days" {
  description = <<-EOT
    How many days the state host's ClickHouse backups are kept in the backups bucket, whole each
    night (ADR-0037): their size times this is what they cost, and an expired one is kept 7 days
    more as an old version. The restore drill's own are kept 7.
    Floci's state services are Fargate tasks, which have none.
  EOT
  type        = number
  default     = 14

  validation {
    condition     = var.clickhouse_backup_retention_days == floor(var.clickhouse_backup_retention_days) && var.clickhouse_backup_retention_days >= 2 && var.clickhouse_backup_retention_days <= 365
    error_message = "ClickHouse's backups are kept a whole number of days, 2 to 365: with fewer, last night's could expire before tonight's is written, and none would be left."
  }
}

variable "destroyable" {
  description = <<-EOT
    Whether a destroy may take everything: RDS without a final snapshot, the buckets emptied, the
    secrets deleted at once, the state host's volume without a snapshot, and the ALB. Only where
    nothing is kept, such as Floci.
  EOT
  type        = bool
  default     = false
}

variable "tls_to_data" {
  description = "Whether the clients require TLS to RDS and ElastiCache: always on AWS; Floci serves neither (ADR-0025)."
  type        = bool
  default     = true
}

variable "aws_endpoint_url" {
  description = "Where the services reach AWS's APIs, such as S3, when it isn't AWS: Floci's address for its tasks."
  type        = string
  default     = null
}

variable "secret_versions" {
  description = <<-EOT
    The version of each secret that may rotate, by its key, 1 by default. Raising one writes it
    again with a new password; db-init runs again for a database's, and each service that reads it
    is deployed again with new tasks. Replacing what a secret's value names, such as RDS behind a
    database's URL, needs its version raised too: the secret is written only when it is.

    `valkey` is Valkey's token, with its connection strings. Raising it also mends an apply that
    stopped after ElastiCache was made but before its secret was written, which leaves the two
    with different tokens.

    The others never change: Langfuse's salt and encryption key, and LiteLLM's salt key, encrypt
    data; Langfuse's project keys and admin password, and Grafana's admin password, are read on
    their first start only; and ClickHouse's passwords reach the state host only when its unit
    restarts.
  EOT
  type        = map(number)
  default     = {}

  validation {
    condition = length(setsubtract(keys(var.secret_versions), [
      "langfuse-nextauth-secret", "litellm-master-key", "gotrue-jwt-secret", "valkey",
      "database-langfuse", "database-litellm", "database-gotrue", "database-grafana", "database-app-owner", "database-app",
    ])) == 0
    error_message = "Only these rotate: langfuse-nextauth-secret, litellm-master-key, gotrue-jwt-secret, valkey, and the database-* secrets (see the description for why the others don't)."
  }
  validation {
    condition     = alltrue([for version in values(var.secret_versions) : version >= 1 && floor(version) == version])
    error_message = "A version is a whole number, from 1."
  }
}

variable "gateway_providers" {
  description = <<-EOT
    The model providers LiteLLM calls, such as anthropic: each gets a secret, <name>/litellm-<provider>-api-key,
    for an operator to write, and LiteLLM gets it as <PROVIDER>_API_KEY. LiteLLM starts once each is written.
  EOT
  type        = set(string)
  default     = []

  validation {
    condition     = alltrue([for provider in var.gateway_providers : can(regex("^[a-z][a-z0-9]*$", provider))])
    error_message = "A provider is lowercase letters and digits, as LiteLLM names it."
  }
}

variable "auth_smtp" {
  description = "The SMTP server GoTrue sends invitations and password resets through; its password is a secret, <name>/auth-smtp-password, for an operator to write. Without it, GoTrue sends no email."
  type = object({
    host   = string
    port   = optional(number, 587)
    user   = string
    sender = string
  })
  default = null
}

variable "langfuse_admin_email" {
  description = "The email of Langfuse's first user, its admin; admin@<domain> by default."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "How long the services' container logs stay in CloudWatch Logs."
  type        = number
  default     = 14
}

variable "run_task_environment" {
  description = <<-EOT
    What the AWS CLI that runs the one-off tasks needs, beside the environment OpenTofu runs in:
    the provider's credentials, when the provider is given them other than through that
    environment, such as AWS_PROFILE. Never a secret's value.
  EOT
  type        = map(string)
  default     = {}
}
