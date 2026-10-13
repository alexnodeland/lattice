output "postgres" {
  description = "RDS: where it is, and the secret RDS keeps its master's password in."
  value = {
    address           = aws_db_instance.this.address
    port              = aws_db_instance.this.port
    master_secret_arn = aws_db_instance.this.master_user_secret[0].secret_arn
  }
}

output "valkey" {
  description = "ElastiCache: where its primary is. Clients use TLS and the auth token."
  value = {
    address = aws_elasticache_replication_group.this.primary_endpoint_address
    port    = var.valkey.port
  }
}

output "security_group_id" {
  description = "The data stores' security group."
  value       = aws_security_group.this.id
}

output "buckets" {
  description = "The buckets, by role: each one's name and ARN."
  value       = { for role, bucket in aws_s3_bucket.this : role => { name = bucket.id, arn = bucket.arn } }
}
