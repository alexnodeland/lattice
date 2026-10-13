# The stack module, planned against a mocked AWS (tier 1, RFC-0004): every module together, as
# envs/prod and envs/floci use it.

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
  mock_data "aws_subnet" {
    defaults = { availability_zone = "us-east-1a" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf" }
  }
  mock_resource "aws_secretsmanager_secret_version" {
    defaults = { secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address            = "stackr.mocked.us-east-1.rds.amazonaws.com"
      port               = 5432
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:rds!db-mocked-AbCdEf", kms_key_id = "", secret_status = "active" }]
    }
  }
  mock_resource "aws_elasticache_replication_group" {
    defaults = { primary_endpoint_address = "master.stackr.mocked.cache.amazonaws.com" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { id = "stackr-mocked", arn = "arn:aws:s3:::stackr-mocked" }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/mocked"
      domain_validation_options = [
        { domain_name = "app.example.com", resource_record_name = "_a.app.example.com.", resource_record_type = "CNAME", resource_record_value = "_a.acm-validations.aws." },
        { domain_name = "auth.example.com", resource_record_name = "_a.auth.example.com.", resource_record_type = "CNAME", resource_record_value = "_b.acm-validations.aws." },
      ]
    }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/stackr/mocked" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/stackr/mocked/mocked" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/stackr/mocked" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mocked" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:000000000000:log-group:/stackr/mocked" }
  }
  mock_resource "aws_ebs_volume" {
    defaults = { id = "vol-0123456789abcdef0" }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = { arn = "arn:aws:servicediscovery:us-east-1:000000000000:service/srv-mocked" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-east-1:000000000000:cluster/stackr" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-1:000000000000:task-definition/stackr-mocked:1" }
  }
}

variables {
  name           = "stackr"
  domain         = "example.com"
  zone_id        = "Z0000000000000"
  zones          = ["us-east-1a", "us-east-1b"]
  lattice_commit = "0123456789abcdef0123456789abcdef01234567"
  ami_id         = "ami-0123456789abcdef0"
  images = {
    otel_collector = "ghcr.io/alexnodeland/stackr-otel-collector@sha256:0000000000000000000000000000000000000000000000000000000000000001"
    tempo          = "ghcr.io/alexnodeland/stackr-tempo@sha256:0000000000000000000000000000000000000000000000000000000000000002"
    loki           = "ghcr.io/alexnodeland/stackr-loki@sha256:0000000000000000000000000000000000000000000000000000000000000003"
    pyroscope      = "ghcr.io/alexnodeland/stackr-pyroscope@sha256:0000000000000000000000000000000000000000000000000000000000000004"
    grafana        = "ghcr.io/alexnodeland/stackr-grafana@sha256:0000000000000000000000000000000000000000000000000000000000000005"
    litellm        = "ghcr.io/alexnodeland/stackr-litellm@sha256:0000000000000000000000000000000000000000000000000000000000000006"
    db_init        = "ghcr.io/alexnodeland/stackr-db-init@sha256:0000000000000000000000000000000000000000000000000000000000000007"
    auth_keys      = "ghcr.io/alexnodeland/stackr-auth-keys@sha256:0000000000000000000000000000000000000000000000000000000000000008"
  }
  application = {
    name  = "acme"
    image = "ghcr.io/example/acme@sha256:0000000000000000000000000000000000000000000000000000000000000009"
  }
}

run "stack_secrets_are_references_never_settings" {
  command = plan
  module {
    source = "./modules/stack"
  }

  assert {
    condition = alltrue(flatten([
      for service in [
        module.app, module.gotrue, module.litellm, module.langfuse_web, module.langfuse_worker, module.grafana,
        module.otel_collector, module.telemetry["tempo"], module.telemetry["loki"], module.telemetry["pyroscope"],
        module.db_init, module.auth_keys, module.db_roles[0],
        ] : [
        for container in service.containers : [
          for setting in container.environment :
          !can(regex("PASSWORD|SECRET|TOKEN|_KEY$|^DATABASE_(ADMIN_)?URL$|^REDIS_|^GOTRUE_DB_DATABASE_URL$|^SALT$", setting.name))
        ]
      ]
    ]))
    error_message = "No password, secret, key, token or URL with credentials is a setting in a task definition."
  }
  assert {
    condition = alltrue(flatten([
      for service in [module.app, module.gotrue, module.litellm, module.langfuse_web, module.db_init] : [
        for container in service.containers : [
          for secret in try(container.secrets, []) : startswith(secret.valueFrom, "arn:aws:secretsmanager:us-east-1:000000000000:secret:")
        ]
      ]
    ]))
    error_message = "Every secret is a reference to Secrets Manager."
  }
}

run "stack_gotrue_listens_on_loopback_behind_its_proxy" {
  command = plan
  module {
    source = "./modules/stack"
  }

  assert {
    condition     = [for container in module.gotrue.containers : container.name] == ["gotrue", "proxy"]
    error_message = "GoTrue's task runs its proxy beside it."
  }
  assert {
    condition = (
      { for setting in module.gotrue.containers[0].environment : setting.name => setting.value }["GOTRUE_API_HOST"] == "127.0.0.1"
      && { for setting in module.gotrue.containers[0].environment : setting.name => setting.value }["PORT"] == "9998"
      && { for setting in module.gotrue.containers[0].environment : setting.name => setting.value }["GOTRUE_RATE_LIMIT_HEADER"] == "X-Forwarded-For"
      && { for setting in module.gotrue.containers[0].environment : setting.name => setting.value }["API_EXTERNAL_URL"] == "https://auth.example.com"
    )
    error_message = "GoTrue listens on the task's loopback, at auth.<domain>, and rate-limits by the address its proxy passes it."
  }
  assert {
    condition     = strcontains(module.gotrue.containers[1].environment[0].value, "trusted_proxies static 10.40.0.0/20 10.40.16.0/20")
    error_message = "The proxy trusts the public subnets, where the ALB is."
  }
}

run "stack_services_find_each_other_and_their_storage" {
  command = plan
  module {
    source = "./modules/stack"
  }

  assert {
    condition = (
      { for setting in module.otel_collector.containers[0].environment : setting.name => setting.value }["TEMPO_ADDRESS"] == "tempo.stackr.internal"
      && { for setting in module.otel_collector.containers[0].environment : setting.name => setting.value }["LANGFUSE_ADDRESS"] == "langfuse-web.stackr.internal"
    )
    error_message = "The Collector finds its peers at their names in stackr.internal."
  }
  assert {
    condition = (
      { for setting in module.telemetry["tempo"].containers[0].environment : setting.name => setting.value }["S3_PREFIX"] == "tempo/"
      && { for setting in module.telemetry["loki"].containers[0].environment : setting.name => setting.value }["S3_BUCKET"] == "stackr-mocked"
    )
    error_message = "Tempo, Loki and Pyroscope keep their blocks in the telemetry bucket, each under its own prefix."
  }
  assert {
    condition = (
      { for secret in module.litellm.containers[0].secrets : secret.name => secret.valueFrom }["REDIS_URL"] == "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf:litellm::"
      && { for secret in module.langfuse_worker.containers[0].secrets : secret.name => secret.valueFrom }["REDIS_CONNECTION_STRING"] == "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf:langfuse::"
    )
    error_message = "LiteLLM and Langfuse each read their own connection string from Valkey's secret."
  }
  assert {
    condition     = { for setting in module.db_init.containers[0].environment : setting.name => setting.value }["PGSSLMODE"] == "require"
    error_message = "db-init requires TLS to RDS."
  }
}

run "stack_the_application_with_grantr" {
  command = plan
  module {
    source = "./modules/stack"
  }

  assert {
    condition     = toset(["DATABASE_URL", "DATABASE_ADMIN_URL", "AUTH_SERVICE_ROLE_KEY", "LANGFUSE_PUBLIC_KEY"]) == setintersection(toset([for secret in module.app.containers[0].secrets : secret.name]), toset(["DATABASE_URL", "DATABASE_ADMIN_URL", "AUTH_SERVICE_ROLE_KEY", "LANGFUSE_PUBLIC_KEY"]))
    error_message = "With grantr, the application works as one role and migrates as the owner, with GoTrue's service role key."
  }
  assert {
    condition     = { for setting in module.app.containers[0].environment : setting.name => setting.value }["AUTH_ADMIN_URL"] == "http://gotrue.stackr.internal:9999"
    error_message = "The application reaches GoTrue's admin API at its private address."
  }
  assert {
    condition = (
      length(module.db_roles) == 1 && module.db_roles[0].containers[0].command == ["acme-admin", "db-roles"]
      && module.db_init.address == null && module.auth_keys.address == null && module.db_roles[0].address == null
    )
    error_message = "db-init, auth-keys and db-roles are one-off tasks; db-roles is the application's admin command."
  }
}

run "stack_the_application_without_access" {
  command = plan
  module {
    source = "./modules/stack"
  }
  variables {
    application = {
      name   = "acme"
      image  = "ghcr.io/example/acme@sha256:0000000000000000000000000000000000000000000000000000000000000009"
      access = "none"
    }
  }

  assert {
    condition     = length(module.db_roles) == 0 && length(terraform_data.db_roles) == 0
    error_message = "Without grantr, there is no db-roles."
  }
  assert {
    condition = (
      contains([for secret in module.app.containers[0].secrets : secret.name], "DATABASE_URL")
      && !contains([for secret in module.app.containers[0].secrets : secret.name], "DATABASE_ADMIN_URL")
    )
    error_message = "Without grantr, the application has one database URL, its owner's."
  }
}

run "stack_the_state_host_on_ec2" {
  command = plan
  module {
    source = "./modules/stack"
  }

  assert {
    condition     = length(module.state_host) == 1 && length(module.state_services) == 0
    error_message = "On AWS, ClickHouse, Prometheus and prom-label-proxy run on the state host."
  }
}

run "stack_the_state_host_on_fargate_for_floci" {
  command = plan
  module {
    source = "./modules/stack"
  }
  variables {
    state_host       = "fargate"
    ami_id           = null
    lattice_commit   = null
    tls_to_data      = false
    destroyable      = true
    aws_endpoint_url = "http://floci:4566"
  }

  assert {
    condition     = length(module.state_host) == 0 && toset(keys(module.state_services)) == toset(["clickhouse", "prometheus", "prom-label-proxy"])
    error_message = "On Floci, the state host's three services run on Fargate."
  }
  assert {
    condition = (
      { for setting in module.db_init.containers[0].environment : setting.name => setting.value }["PGSSLMODE"] == "prefer"
      && { for setting in module.grafana.containers[0].environment : setting.name => setting.value }["GF_DATABASE_SSL_MODE"] == "disable"
      && { for setting in module.langfuse_web.containers[0].environment : setting.name => setting.value }["LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT"] == "http://floci:4566"
    )
    error_message = "Without TLS to the data stores, and with S3 at Floci's address."
  }
  assert {
    condition     = aws_secretsmanager_secret.valkey.recovery_window_in_days == 0
    error_message = "A destroyable deployment deletes its secrets at once."
  }
}

run "stack_refuses_to_rotate_what_encrypts_data" {
  command = plan
  module {
    source = "./modules/stack"
  }
  variables {
    secret_versions = { langfuse-encryption-key = 2 }
  }
  expect_failures = [var.secret_versions]
}

run "stack_refuses_the_state_host_without_its_ami" {
  command = plan
  module {
    source = "./modules/stack"
  }
  variables {
    ami_id = null
  }
  expect_failures = [var.ami_id]
}
