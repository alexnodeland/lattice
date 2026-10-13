variable "images" {
  description = "stackr's thin images, as tier 2 builds them."
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
  description = "The application tier 2 deploys: one generated from stackr's template."
  type = object({
    name        = string
    image       = string
    access      = optional(string, "grantr")
    environment = optional(map(string), {})
    secrets     = optional(map(string), {})
  })
}

variable "endpoint_for_tasks" {
  description = "Floci's address as the tasks reach it, on the Docker network Floci runs them on."
  type        = string
  default     = "http://floci:4566"
}
