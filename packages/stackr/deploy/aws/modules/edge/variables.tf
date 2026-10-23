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
    condition     = can(regex("^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}$", var.domain))
    error_message = "A domain is labels of lowercase letters, digits and inner hyphens, joined by dots."
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

variable "public_subnet_cidrs" {
  description = "The public subnets' ranges: the only addresses GoTrue's proxy takes X-Forwarded-For from."
  type        = list(string)

  validation {
    condition     = length(var.public_subnet_cidrs) > 0 && alltrue([for cidr in var.public_subnet_cidrs : can(cidrhost(cidr, 0))])
    error_message = "Name each public subnet's range, in CIDR notation."
  }
}

variable "access_logs" {
  description = "The bucket, from data, and the prefix ELB may write the ALB's access logs under."
  type = object({
    bucket = string
    prefix = string
  })
}

variable "caddy_image" {
  description = "Caddy's image for GoTrue's proxy, pinned as the single host's edge is."
  type        = string
  default     = "caddy:2.11.7-alpine@sha256:eb4d35b7452d1ab6171fbdbe8d9275b2301dad6dad92115d91e19fb9b24d510f"
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
