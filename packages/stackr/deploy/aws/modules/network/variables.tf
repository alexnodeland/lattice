variable "name" {
  description = "The deployment's name, which every resource's name and tags start with."
  type        = string
}

variable "cidr" {
  description = "The VPC's address range; each zone gets a public and a private /20 of it."
  type        = string
  default     = "10.40.0.0/16"
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
  description = "How long the VPC's flow logs are kept, in days."
  type        = number
  default     = 30
}
