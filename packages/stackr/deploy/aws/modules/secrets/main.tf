# The deployment's secrets, in Secrets Manager (RFC-0004). A generated secret is never in state:
# its password is ephemeral, and reaches Secrets Manager through a write-only argument, written
# once, and again only when its version is raised. ECS injects each into its tasks by ARN.

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
  secret_string_wo = each.value.keys == null ? ephemeral.random_password.this[each.key].result : jsonencode({
    for key, template in each.value.keys :
    key => replace(template, "{password}", ephemeral.random_password.this[each.key].result)
  })
  secret_string_wo_version = each.value.version
}

resource "aws_secretsmanager_secret" "written_elsewhere" {
  for_each                = var.written_elsewhere
  name                    = "${var.name}/${each.key}"
  recovery_window_in_days = var.recovery_window_in_days
}
