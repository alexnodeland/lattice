variable "name" {
  description = "The deployment's name: each secret is <name>/<key>."
  type        = string
}

variable "generated" {
  description = <<-EOT
    Secrets made here, each from a password made for it alone: the password itself, or, with
    `keys`, a JSON object whose values are templates, `{password}` where the password goes.
    `version` writes it again when raised.
  EOT
  type = map(object({
    length  = optional(number, 48)
    keys    = optional(map(string))
    version = optional(number, 1)
  }))
  default = {}
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
}
