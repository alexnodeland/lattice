# ElastiCache for Valkey (RFC-0004): Langfuse's queues and the gateway's cache, with `noeviction`
# so queued jobs are never dropped, encrypted in transit and at rest, behind an auth token that
# reaches it through a write-only argument, never through state.

resource "aws_elasticache_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_parameter_group" "this" {
  name   = "${var.name}-valkey8"
  family = "valkey8"

  parameter {
    name  = "maxmemory-policy"
    value = "noeviction"
  }
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = var.name
  description                = "${var.name}: Langfuse's queues and the gateway's cache"
  engine                     = "valkey"
  engine_version             = "8.1"
  node_type                  = var.valkey.node_type
  port                       = var.valkey.port
  num_cache_clusters         = 1
  automatic_failover_enabled = false
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.this.id]
  parameter_group_name       = aws_elasticache_parameter_group.this.name
  transit_encryption_enabled = true
  at_rest_encryption_enabled = true
  auth_token_wo              = var.valkey_auth_token
  auth_token_wo_version      = var.valkey.auth_token_wo_version
  snapshot_retention_limit   = var.valkey.snapshot_retention
  auto_minor_version_upgrade = true
}
