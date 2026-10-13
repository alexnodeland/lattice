variable "name" {
  description = "The deployment's name: each secret is <name>/<key>."
  type        = string

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,19}$", var.name))
    error_message = "A name is 2 to 20 lowercase letters, digits and hyphens, starting with a letter."
  }
}

variable "generated" {
  description = <<-EOT
    Secrets made here, each from a password made for it alone: the password itself, or, with
    `keys`, a JSON object whose values are templates, `{password}` where the password goes.
    `version` writes it again when raised, with a new password: a changed template, such as a
    database's new address, needs a raised version too, and so rotates the secret.
  EOT
  type = map(object({
    length  = optional(number, 48)
    keys    = optional(map(string))
    version = optional(number, 1)
  }))
  default = {}

  validation {
    condition     = alltrue([for secret in var.generated : secret.length >= 16 && secret.length <= 128])
    error_message = "A generated password is 16 to 128 characters."
  }
}

variable "written_elsewhere" {
  description = "Secrets this makes empty, for something else to write: a one-off task, or an operator."
  type        = set(string)
  default     = []
}

variable "recovery_window_in_days" {
  description = "How long a deleted secret can still be restored; 0 deletes it at once."
  type        = number
  default     = 30

  validation {
    condition     = var.recovery_window_in_days == 0 || (var.recovery_window_in_days >= 7 && var.recovery_window_in_days <= 30)
    error_message = "Secrets Manager takes 0, or 7 to 30 days."
  }
}
