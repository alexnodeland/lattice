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
  description = "The private DNS namespace (Cloud Map) it is named in, as <name>.<namespace>."
  type        = string
}

variable "container" {
  description = "Its one container: image (by digest), port, command, environment, and secrets, each a Secrets Manager ARN, or <arn>:<json key>::."
  type = object({
    image       = string
    port        = optional(number)
    command     = optional(list(string))
    environment = optional(map(string), {})
    secrets     = optional(map(string), {})
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

variable "target_group_arn" {
  description = "The ALB target group its tasks register with, when the edge reaches it."
  type        = string
  default     = null
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
