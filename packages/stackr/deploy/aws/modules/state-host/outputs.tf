output "address" {
  description = "The state host's fixed private address."
  value       = var.private_ip
}

output "instance_id" {
  description = "The instance, which SSM port forwarding names as its target."
  value       = aws_instance.this.id
}

output "secret_arns" {
  description = "The two secrets it reads: ClickHouse's passwords for Langfuse and for the admin."
  value = {
    clickhouse_password       = var.clickhouse_password_secret_arn
    clickhouse_admin_password = var.clickhouse_admin_password_secret_arn
  }
}
