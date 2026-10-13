variable "region" {
  description = "The AWS region the deployment is in."
  type        = string
}

variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string
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
  description = "Two availability zones in the region."
  type        = list(string)
}

variable "ami_id" {
  description = "The state host's AMI, pinned: bumped on purpose (stackr ADR-0032)."
  type        = string
}

variable "lattice_commit" {
  description = "The commit of lattice, by its full SHA, the state host checks out: the stackr release's."
  type        = string
}

variable "images" {
  # Pinned here, with Renovate moving them, once stackr's release publishes them (RFC-0004).
  description = "stackr's thin images, by digest, from its release (stackr ADR-0034)."
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
  description = "The application: its name (project_slug), image by digest, access, and its own settings and secrets."
  type = object({
    name        = string
    image       = string
    access      = optional(string, "grantr")
    environment = optional(map(string), {})
    secrets     = optional(map(string), {})
  })
}

variable "gateway_providers" {
  description = "The model providers LiteLLM calls, each with a secret an operator writes."
  type        = set(string)
  default     = []
}

variable "auth_smtp" {
  description = "The SMTP server GoTrue sends email through; none by default."
  type = object({
    host   = string
    port   = optional(number, 587)
    user   = string
    sender = string
  })
  default = null
}

variable "secret_versions" {
  description = "Each generated secret's version, by its key: raising one rotates it."
  type        = map(number)
  default     = {}
}
