# The data module, against a mocked AWS (tier 1, RFC-0004): planned, or applied where only an
# apply knows a value, such as a bucket's ARN in its policy.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:rds", kms_key_id = "", secret_status = "active" }]
    }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { arn = "arn:aws:s3:::stackr-mocked" }
  }
}

variables {
  name              = "stackr"
  vpc_id            = "vpc-mocked"
  subnet_ids        = ["subnet-a", "subnet-b"]
  valkey_auth_token = "a-mocked-auth-token-of-48-characters-for-valkey00"
}

run "data_postgres_17_encrypted_with_tls_required_and_kept_on_destroy" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_db_instance.this.engine_version == "17" && aws_db_instance.this.username == "postgres" && aws_db_instance.this.manage_master_user_password
    error_message = "PostgreSQL 17, its master named postgres for GoTrue's migrations, with the password RDS manages."
  }
  assert {
    condition     = aws_db_instance.this.storage_encrypted && !aws_db_instance.this.publicly_accessible
    error_message = "RDS is encrypted, and never public."
  }
  assert {
    condition     = one([for parameter in aws_db_parameter_group.this.parameter : parameter.value if parameter.name == "rds.force_ssl"]) == "1"
    error_message = "RDS requires TLS."
  }
  assert {
    condition     = aws_db_instance.this.deletion_protection && !aws_db_instance.this.skip_final_snapshot && aws_db_instance.this.backup_retention_period >= 1
    error_message = "By default, RDS keeps backups, refuses to be deleted, and takes a final snapshot."
  }
}

run "data_a_destroyable_deployment_keeps_nothing" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    postgres              = { deletion_protection = false, skip_final_snapshot = true }
    force_destroy_buckets = true
  }

  assert {
    condition     = aws_db_instance.this.final_snapshot_identifier == null && alltrue([for bucket in aws_s3_bucket.this : bucket.force_destroy])
    error_message = "Without a final snapshot, none is named, and a destroy empties the buckets."
  }
}

run "data_refuses_rds_without_backups" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    postgres = { backup_retention_days = 0 }
  }
  expect_failures = [var.postgres]
}

run "data_valkey_never_evicts_needs_tls_and_its_token_on_its_port" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    valkey = { port = 6401, auth_token_wo_version = 2 }
  }

  assert {
    condition     = one([for parameter in aws_elasticache_parameter_group.this.parameter : parameter.value if parameter.name == "maxmemory-policy"]) == "noeviction"
    error_message = "Langfuse's queued jobs must not be evicted."
  }
  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled && aws_elasticache_replication_group.this.at_rest_encryption_enabled
    error_message = "Valkey is encrypted in transit and at rest."
  }
  assert {
    condition     = aws_elasticache_replication_group.this.port == 6401
    error_message = "Valkey listens on its port."
  }
  assert {
    condition     = aws_elasticache_replication_group.this.auth_token_wo_version == 2
    error_message = "Raising the token's version writes it again."
  }
}

run "data_refuses_a_short_auth_token" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    valkey_auth_token = "too-short"
  }
  expect_failures = [var.valkey_auth_token]
}

run "data_expires_clickhouse_backups_by_prefix_in_the_backups_bucket_alone" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition = (
      { for rule in aws_s3_bucket_lifecycle_configuration.this["backups"].rule : rule.id => rule.expiration[0].days if rule.id == "expire-clickhouse" || rule.id == "expire-drill" }
      == { "expire-clickhouse" = 14, "expire-drill" = 7 }
      && alltrue([for rule in aws_s3_bucket_lifecycle_configuration.this["backups"].rule : rule.noncurrent_version_expiration[0].noncurrent_days == 7 if startswith(rule.id, "expire-")])
    )
    error_message = "ClickHouse's backups are kept 14 days and the drill's 7, each with its overwritten versions gone after 7 days."
  }
  assert {
    condition = (
      { for rule in aws_s3_bucket_lifecycle_configuration.this["backups"].rule : rule.id => rule.filter[0].prefix if startswith(rule.id, "expire-") || startswith(rule.id, "markers-") }
      == { "expire-clickhouse" = "clickhouse/", "expire-drill" = "drill/", "markers-clickhouse" = "clickhouse/", "markers-drill" = "drill/" }
      && alltrue([for rule in aws_s3_bucket_lifecycle_configuration.this["backups"].rule : rule.expiration[0].expired_object_delete_marker if startswith(rule.id, "markers-")])
    )
    error_message = "Each rule is for one prefix, and a delete marker left by ClickHouse's lock files expires."
  }
  assert {
    condition     = alltrue([for role, lifecycle in aws_s3_bucket_lifecycle_configuration.this : length(lifecycle.rule) == 1 if role != "backups"])
    error_message = "No other bucket has a rule but the tidy one."
  }
}

run "data_keeps_clickhouse_backups_as_long_as_it_is_told_and_the_drills_for_seven" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    clickhouse_backup_retention_days = 30
  }

  assert {
    condition     = { for rule in aws_s3_bucket_lifecycle_configuration.this["backups"].rule : rule.id => rule.expiration[0].days if rule.id == "expire-clickhouse" || rule.id == "expire-drill" } == { "expire-clickhouse" = 30, "expire-drill" = 7 }
    error_message = "The retention is the variable's, and the drill's stays 7."
  }
}

run "data_refuses_a_retention_under_two_days" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    clickhouse_backup_retention_days = 1
  }
  expect_failures = [var.clickhouse_backup_retention_days]
}

run "data_refuses_a_retention_over_a_year" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    clickhouse_backup_retention_days = 366
  }
  expect_failures = [var.clickhouse_backup_retention_days]
}

run "data_refuses_a_retention_that_is_not_whole_days" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    clickhouse_backup_retention_days = 14.5
  }
  expect_failures = [var.clickhouse_backup_retention_days]
}

run "data_reaches_nothing" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition     = length(aws_security_group.this.egress) == 0 && length(aws_security_group.this.ingress) == 0
    error_message = "The data stores' group reaches nothing, and takes only the rules the stack gives each store's clients."
  }
}

run "data_buckets_are_private_encrypted_versioned_tidied_and_tls_only" {
  command = apply
  module {
    source = "./modules/data"
  }

  assert {
    condition     = alltrue([for bucket in aws_s3_bucket.this : startswith(bucket.bucket_prefix, "stackr-")])
    error_message = "Each bucket's name is unique, after <name>-<role>-."
  }
  assert {
    condition = alltrue([
      for block in aws_s3_bucket_public_access_block.this :
      block.block_public_acls && block.block_public_policy && block.ignore_public_acls && block.restrict_public_buckets
    ])
    error_message = "Every bucket blocks public access."
  }
  assert {
    condition     = alltrue([for versioning in aws_s3_bucket_versioning.this : versioning.versioning_configuration[0].status == "Enabled"])
    error_message = "Every bucket is versioned."
  }
  assert {
    condition     = alltrue([for lifecycle in aws_s3_bucket_lifecycle_configuration.this : lifecycle.rule[0].abort_incomplete_multipart_upload[0].days_after_initiation == 7])
    error_message = "Every bucket drops abandoned uploads."
  }
  assert {
    condition = alltrue([
      for policy in aws_s3_bucket_policy.this :
      jsondecode(policy.policy).Statement[0].Effect == "Deny" && jsondecode(policy.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    ])
    error_message = "Every bucket refuses requests without TLS."
  }
  assert {
    condition = (
      length(jsondecode(aws_s3_bucket_policy.this["langfuse"].policy).Statement) == 1
      && jsondecode(aws_s3_bucket_policy.this["access-logs"].policy).Statement[1] == {
        Sid       = "ELBAccessLogs"
        Effect    = "Allow"
        Principal = { Service = "logdelivery.elasticloadbalancing.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "arn:aws:s3:::stackr-mocked/alb/AWSLogs/000000000000/*"
        Condition = { ArnLike = { "aws:SourceArn" = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/*" } }
      }
    )
    error_message = "ELB's log delivery may write to the access-logs bucket, under alb/, for this account's load balancers only; to no other."
  }
}
