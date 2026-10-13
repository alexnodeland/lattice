variable "name" {
  description = "The deployment's name, which every resource's name starts with."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "domain" {
  description = "The domain the edge serves: the application at app.<domain>, GoTrue at auth.<domain>."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9.-]+$", var.domain))
    error_message = "A domain is lowercase letters, digits, dots and hyphens."
  }
}

variable "zone_id" {
  description = "The Route 53 hosted zone of the domain, which validates the certificate and names the ALB."
  type        = string
}

variable "vpc_id" {
  description = "The VPC the target groups are in."
  type        = string
}

variable "subnet_ids" {
  description = "The public subnets, in two zones, the ALB lives in."
  type        = list(string)
}

variable "security_group_id" {
  description = "The ALB's security group: 443, and 80 to redirect, from anywhere."
  type        = string
}

variable "deletion_protection" {
  description = "Whether the ALB refuses to be deleted."
  type        = bool
  default     = true
}
