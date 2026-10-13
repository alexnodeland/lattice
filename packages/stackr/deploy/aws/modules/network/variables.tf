variable "name" {
  description = "The deployment's name, which every resource's name and tags start with."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "cidr" {
  description = "The VPC's address range, a /16: each zone gets a public and a private /20 of it."
  type        = string
  default     = "10.40.0.0/16"

  validation {
    condition     = can(cidrhost(var.cidr, 0)) && endswith(var.cidr, "/16")
    error_message = "The VPC's range is a /16, which the subnets' /20s are cut from."
  }
}

variable "zones" {
  description = "Two availability zones: the ALB needs subnets in two."
  type        = list(string)

  validation {
    condition     = length(var.zones) == 2
    error_message = "Name exactly two availability zones."
  }
}

variable "flow_log_retention_days" {
  description = "How long the VPC's flow logs are kept, in days: a value CloudWatch Logs accepts."
  type        = number
  default     = 30

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653], var.flow_log_retention_days)
    error_message = "CloudWatch Logs keeps logs for 1, 3, 5, 7, 14, 30, 60, 90 days or more, from its own list."
  }
}
