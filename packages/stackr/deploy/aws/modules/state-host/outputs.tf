output "address" {
  description = "The state host's fixed private address."
  value       = var.private_ip
}

output "instance_id" {
  description = "The instance, which SSM port forwarding names as its target."
  value       = aws_instance.this.id
}

output "secret_arns" {
  description = "The three secrets it reads: ClickHouse's passwords for Langfuse, for the admin and for the backup user."
  value = {
    clickhouse_password        = var.clickhouse_password_secret_arn
    clickhouse_admin_password  = var.clickhouse_admin_password_secret_arn
    clickhouse_backup_password = var.clickhouse_backup_password_secret_arn
  }
}

output "security_group_id" {
  description = "Its security group, which the stack gives the rules to and from the services."
  value       = aws_security_group.this.id
}
