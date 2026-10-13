variable "name" {
  description = "The service's name: its task family, log group and private name are <deployment>-<name>."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.name))
    error_message = "A service's name is lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "deployment" {
  description = "The deployment's name."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.deployment))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "cluster_arn" {
  description = "The ECS cluster."
  type        = string
}

variable "subnet_ids" {
  description = "The private subnets its tasks run in."
  type        = list(string)
}

variable "security_group_ids" {
  description = "Its tasks' security groups."
  type        = list(string)
}

variable "namespace_id" {
  description = "The private DNS namespace (Cloud Map) it is named in, as <name>.<namespace>; none for a one-off task."
  type        = string
  default     = null

  validation {
    condition     = var.one_off || var.namespace_id != null
    error_message = "A service is named in a namespace: give it one."
  }
}

variable "container" {
  description = <<-EOT
    Its container: image (by digest), port, command, environment, and secrets, each a Secrets
    Manager ARN, or <arn>:<json key>::; and whether its root filesystem is read-only.
  EOT
  type = object({
    image                    = string
    port                     = optional(number)
    command                  = optional(list(string))
    environment              = optional(map(string), {})
    secrets                  = optional(map(string), {})
    readonly_root_filesystem = optional(bool, false)
  })

  validation {
    condition     = length(setintersection(keys(var.container.environment), keys(var.container.secrets))) == 0
    error_message = "A setting is either in the environment or a secret, never both."
  }
  validation {
    condition     = alltrue([for value in values(var.container.secrets) : can(regex("^arn:[^:]+:secretsmanager:[^:]+:[0-9]{12}:secret:[^:]+(:[^:]*:[^:]*:[^:]*)?$", value))])
    error_message = "A secret is a Secrets Manager ARN, or <arn>:<json key>:<version stage>:<version id>."
  }
}

variable "proxy" {
  description = <<-EOT
    A Caddy in front of the container, in its task, such as GoTrue's (the edge's auth_proxy): its
    image, and its Caddyfile. It takes the container's port, which the edge and the other services
    reach, and the container listens on the task's loopback, at a port of its own.
  EOT
  type = object({
    image     = string
    caddyfile = string
  })
  default = null

  validation {
    condition     = var.proxy == null || var.container.port != null
    error_message = "A proxy takes the container's port: give the container one."
  }
}

variable "ecr_repository_arns" {
  description = "The ECR repositories its image comes from, which the execution role may pull from; none for a public registry."
  type        = list(string)
  default     = []
}

variable "size" {
  description = "Its tasks' CPU units and memory (MiB), as Fargate sizes them."
  type = object({
    cpu    = optional(number, 512)
    memory = optional(number, 1024)
  })
  default = {}
}

variable "desired_count" {
  description = "How many tasks the service keeps running."
  type        = number
  default     = 1
}

variable "one_off" {
  description = "A task that runs once, by run-task, such as db-init: its definition, with no service and no name."
  type        = bool
  default     = false
}

variable "after" {
  description = "The one-off runs, by name, the service waits for: it starts after them, and starts again after each new run."
  type        = map(string)
  default     = {}
}

variable "target_group_arn" {
  description = "The ALB target group its tasks register with, when the edge reaches it."
  type        = string
  default     = null

  validation {
    condition     = var.target_group_arn == null || (var.container.port != null && !var.one_off)
    error_message = "A target group needs a service with a port: never a one-off task."
  }
}

variable "task_role_policy_json" {
  description = "What its tasks may do in AWS, such as Langfuse's S3 bucket; none by default."
  type        = string
  default     = null
}

variable "log_retention_days" {
  description = "How long its container logs stay in CloudWatch Logs, for when the Collector itself is down."
  type        = number
  default     = 14

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365], var.log_retention_days)
    error_message = "CloudWatch Logs keeps logs for 1, 3, 5, 7, 14, 30, 60, 90 days or more, from its own list."
  }
}
