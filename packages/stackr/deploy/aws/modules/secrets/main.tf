# The deployment's secrets, in Secrets Manager (RFC-0004). A generated secret is never in state:
# its password is ephemeral, and reaches Secrets Manager through a write-only argument, written
# once, and again only when its version is raised. ECS injects each into its tasks by ARN.
#
# A template puts the password where `{password}` is, and its SHA-256, 64 hexadecimal characters,
# where `{password_sha256}` is, for a setting that must be hexadecimal.

ephemeral "random_password" "this" {
  for_each = var.generated
  length   = each.value.length
  special  = false
}

resource "aws_secretsmanager_secret" "generated" {
  for_each                = var.generated
  name                    = "${var.name}/${each.key}"
  recovery_window_in_days = var.recovery_window_in_days
}

resource "aws_secretsmanager_secret_version" "generated" {
  for_each  = var.generated
  secret_id = aws_secretsmanager_secret.generated[each.key].id
  secret_string_wo = each.value.keys == null ? replace(
    replace(each.value.template, "{password_sha256}", sha256(ephemeral.random_password.this[each.key].result)),
    "{password}", ephemeral.random_password.this[each.key].result,
    ) : jsonencode({
      for key, template in each.value.keys : key => replace(
        replace(template, "{password_sha256}", sha256(ephemeral.random_password.this[each.key].result)),
        "{password}", ephemeral.random_password.this[each.key].result,
      )
  })
  secret_string_wo_version = each.value.version
}

resource "aws_secretsmanager_secret" "written_elsewhere" {
  for_each                = var.written_elsewhere
  name                    = "${var.name}/${each.key}"
  recovery_window_in_days = var.recovery_window_in_days
}
