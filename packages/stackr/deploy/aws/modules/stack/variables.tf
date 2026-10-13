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
    Each generated secret's version, by its key, 1 by default: raising one writes it again with a
    new password, and reruns the one-off tasks that read it. `valkey` is Valkey's token and its
    connection strings; `langfuse-keys` Langfuse's project keys. Langfuse's salt and encryption
    key, and LiteLLM's salt key, encrypt data, and never change.
  EOT
  type        = map(number)
  default     = {}

  validation {
    condition     = length(setintersection(keys(var.secret_versions), ["langfuse-salt", "langfuse-encryption-key", "litellm-salt-key"])) == 0
    error_message = "Langfuse's salt and encryption key, and LiteLLM's salt key, encrypt data: they never change."
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
