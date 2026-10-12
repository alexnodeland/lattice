# RDS for PostgreSQL 17 (RFC-0004): one instance, in the private subnets, encrypted, with TLS
# required. Its master is `postgres`, since GoTrue's migrations grant to that role (stackr
# ADR-0025), and its password is RDS's own, in a secret RDS manages.

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_db_parameter_group" "this" {
  name_prefix = "${var.name}-postgres17-"
  family      = "postgres17"

  lifecycle {
    create_before_destroy = true
  }

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "1000"
  }
}

# A final snapshot's name is unique to this instance, so a second deployment of the same name
# doesn't collide with the first's.
resource "random_id" "final_snapshot" {
  byte_length = 4
}

resource "aws_db_instance" "this" {
  identifier                          = var.name
  engine                              = "postgres"
  engine_version                      = "17"
  instance_class                      = var.postgres.instance_class
  allocated_storage                   = var.postgres.allocated_storage
  max_allocated_storage               = var.postgres.max_allocated_storage
  storage_type                        = "gp3"
  storage_encrypted                   = true
  username                            = "postgres"
  manage_master_user_password         = true
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.this.id]
  parameter_group_name                = aws_db_parameter_group.this.name
  publicly_accessible                 = false
  multi_az                            = false
  backup_retention_period             = var.postgres.backup_retention_days
  copy_tags_to_snapshot               = true
  auto_minor_version_upgrade          = true
  enabled_cloudwatch_logs_exports     = ["postgresql", "upgrade"]
  performance_insights_enabled        = true
  iam_database_authentication_enabled = true
  deletion_protection                 = var.postgres.deletion_protection
  skip_final_snapshot                 = var.postgres.skip_final_snapshot
  final_snapshot_identifier           = var.postgres.skip_final_snapshot ? null : "${var.name}-final-${random_id.final_snapshot.hex}"
}
