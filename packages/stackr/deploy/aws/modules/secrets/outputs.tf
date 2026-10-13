output "arns" {
  description = "Each secret's ARN, by its key: ECS injects it whole, or one of its JSON keys as <arn>:<key>::."
  value = merge(
    { for key, secret in aws_secretsmanager_secret.generated : key => secret.arn },
    { for key, secret in aws_secretsmanager_secret.written_elsewhere : key => secret.arn },
  )
  # The versions are written before anything reads the secrets.
  depends_on = [aws_secretsmanager_secret_version.generated]
}
