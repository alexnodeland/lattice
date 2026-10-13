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
    Secrets made here, each from a password made for it alone: its `template`, the password
    itself by default; or, with `keys`, a JSON object whose values are templates. A template has
    `{password}` where the password goes, and `{password_sha256}` where its SHA-256 goes, in
    hexadecimal. `version` writes it again when raised, with a new password: a changed template,
    such as a database's new address, needs a raised version too, and so rotates the secret.
  EOT
  type = map(object({
    length   = optional(number, 48)
    template = optional(string, "{password}")
    keys     = optional(map(string))
    version  = optional(number, 1)
  }))
  default = {}

  validation {
    condition     = alltrue([for secret in var.generated : secret.length >= 16 && secret.length <= 128])
    error_message = "A generated password is 16 to 128 characters."
  }
  validation {
    condition = alltrue(flatten([
      for secret in var.generated : [
        for template in secret.keys == null ? [secret.template] : values(secret.keys) :
        strcontains(template, "{password}") || strcontains(template, "{password_sha256}")
      ]
    ]))
    error_message = "Each template holds the password, or its SHA-256: one without would be written as it is."
  }
  validation {
    condition     = alltrue([for secret in var.generated : secret.keys == null || secret.template == "{password}"])
    error_message = "A secret is a template, or keys of templates, never both."
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
