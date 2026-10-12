# The data module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{\"Version\": \"2012-10-17\", \"Statement\": []}" }
  }
  # The secret RDS manages for its master, as the module reads it.
  mock_resource "aws_db_instance" {
    defaults = {
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:rds", kms_key_id = "", secret_status = "active" }]
    }
  }
}

variables {
  name              = "stackr"
  subnet_ids        = ["subnet-a", "subnet-b"]
  security_group_id = "sg-data"
  valkey_auth_token = "a-mocked-auth-token-of-48-characters-for-valkey00"
}

run "data_postgres_17_with_tls_required_and_kept_on_destroy" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition     = aws_db_instance.this.engine_version == "17" && aws_db_instance.this.username == "postgres"
    error_message = "PostgreSQL 17, with its master named postgres for GoTrue's migrations."
  }
  assert {
    condition     = one([for parameter in aws_db_parameter_group.this.parameter : parameter.value if parameter.name == "rds.force_ssl"]) == "1"
    error_message = "RDS requires TLS."
  }
  assert {
    condition     = aws_db_instance.this.deletion_protection && !aws_db_instance.this.skip_final_snapshot && !aws_db_instance.this.publicly_accessible
    error_message = "By default, a destroy keeps RDS: protected, with a final snapshot, and never public."
  }
}

run "data_a_destroyable_deployment_where_nothing_is_kept" {
  command = plan
  module {
    source = "./modules/data"
  }
  variables {
    postgres              = { deletion_protection = false, skip_final_snapshot = true }
    force_destroy_buckets = true
  }

  assert {
    condition     = aws_db_instance.this.final_snapshot_identifier == null
    error_message = "Without a final snapshot, none is named."
  }
}

run "data_valkey_never_evicts_and_needs_tls_and_a_token" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition     = one([for parameter in aws_elasticache_parameter_group.this.parameter : parameter.value if parameter.name == "maxmemory-policy"]) == "noeviction"
    error_message = "Langfuse's queued jobs must not be evicted."
  }
  assert {
    condition     = aws_elasticache_replication_group.this.transit_encryption_enabled && aws_elasticache_replication_group.this.at_rest_encryption_enabled
    error_message = "Valkey is encrypted in transit and at rest."
  }
}

run "data_no_bucket_is_public" {
  command = plan
  module {
    source = "./modules/data"
  }

  assert {
    condition = alltrue([
      for block in aws_s3_bucket_public_access_block.this :
      block.block_public_acls && block.block_public_policy && block.ignore_public_acls && block.restrict_public_buckets
    ])
    error_message = "Every bucket blocks public access."
  }
}
