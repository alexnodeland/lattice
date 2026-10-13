# The deployment's secrets (RFC-0004), never in state. Most are the secrets module's: a password
# each, written once. The databases' are a second instance of it, since their URLs carry RDS's
# address. Two are written here, each from passwords the module can't combine: Valkey's token,
# which ElastiCache is given too, with the connection strings that carry it; and Langfuse's project
# keys, with the Collector's Basic credential made of both.

module "secrets" {
  source                  = "../secrets"
  name                    = var.name
  recovery_window_in_days = local.recovery_window
  generated = { for key, secret in merge(
    {
      langfuse-salt            = {}
      langfuse-encryption-key  = { template = "{password_sha256}" }
      langfuse-nextauth-secret = {}
      langfuse-admin-password  = {}
      litellm-master-key       = { template = "sk-{password}" }
      litellm-salt-key         = {}
      grafana-admin-password   = {}
      gotrue-jwt-secret        = {}
      clickhouse-password      = {}
    },
    # ClickHouse's admin is the state host's users.xml's: Floci's ClickHouse has none.
    { for key, secret in { clickhouse-admin-password = {} } : key => secret if var.state_host == "ec2" },
  ) : key => merge(secret, { version = lookup(var.secret_versions, key, 1) }) }
  # GoTrue's key set and the service role's key, which the auth-keys task writes, each a secret of
  # its own, as GoTrue and the application read them whole; and the
  # operator's.
  written_elsewhere = setunion(
    ["auth-jwt-keys", "auth-service-role-key"],
    [for provider in var.gateway_providers : "litellm-${provider}-api-key"],
    var.auth_smtp == null ? [] : ["auth-smtp-password"],
  )
}

locals {
  # A deleted secret can be restored for 30 days, but where a destroy takes everything.
  recovery_window = var.destroyable ? 0 : 30
  postgres        = "${module.data.postgres.address}:${module.data.postgres.port}"
  # Each database's role's password, and its URL, as its client takes it.
  databases = merge(
    {
      langfuse  = { url = "postgresql://langfuse:{password}@${local.postgres}/langfuse?sslmode=${local.postgres_tls}" }
      litellm   = { url = "postgresql://litellm:{password}@${local.postgres}/litellm?sslmode=${local.postgres_tls}" }
      gotrue    = { url = "postgres://gotrue:{password}@${local.postgres}/auth?sslmode=${local.postgres_tls}" }
      grafana   = {}
      app-owner = { url = "postgresql+asyncpg://${local.app_database}:{password}@${local.postgres}/${local.app_database}?ssl=${local.postgres_tls}" }
    },
    local.grantr ? {
      app = { url = "postgresql+asyncpg://${local.app_database}_app:{password}@${local.postgres}/${local.app_database}?ssl=${local.postgres_tls}" }
    } : {},
  )
}

module "databases" {
  source                  = "../secrets"
  name                    = var.name
  recovery_window_in_days = local.recovery_window
  generated = { for role, database in local.databases : "database-${role}" => {
    keys    = merge({ password = "{password}" }, database)
    version = lookup(var.secret_versions, "database-${role}", 1)
  } }
}

# Valkey's token, and the connection strings that carry it: Langfuse's database 0, LiteLLM's 1.
ephemeral "random_password" "valkey" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "valkey" {
  name                    = "${var.name}/valkey"
  recovery_window_in_days = local.recovery_window
}

resource "aws_secretsmanager_secret_version" "valkey" {
  secret_id = aws_secretsmanager_secret.valkey.id
  secret_string_wo = jsonencode({
    token    = ephemeral.random_password.valkey.result
    langfuse = "${var.tls_to_data ? "rediss" : "redis"}://:${ephemeral.random_password.valkey.result}@${module.data.valkey.address}:${module.data.valkey.port}/0"
    litellm  = "${var.tls_to_data ? "rediss" : "redis"}://:${ephemeral.random_password.valkey.result}@${module.data.valkey.address}:${module.data.valkey.port}/1"
  })
  secret_string_wo_version = lookup(var.secret_versions, "valkey", 1)
}

# Langfuse's project keys, which its first start creates the project with, and the Collector's
# Basic credential for Langfuse's OTLP endpoint, made of both.
ephemeral "random_password" "langfuse_key" {
  for_each = toset(["public", "secret"])
  length   = 48
  special  = false
}

resource "aws_secretsmanager_secret" "langfuse_keys" {
  name                    = "${var.name}/langfuse-keys"
  recovery_window_in_days = local.recovery_window
}

resource "aws_secretsmanager_secret_version" "langfuse_keys" {
  secret_id = aws_secretsmanager_secret.langfuse_keys.id
  secret_string_wo = jsonencode({
    public    = "pk-lf-${ephemeral.random_password.langfuse_key["public"].result}"
    secret    = "sk-lf-${ephemeral.random_password.langfuse_key["secret"].result}"
    otlp_auth = base64encode("pk-lf-${ephemeral.random_password.langfuse_key["public"].result}:sk-lf-${ephemeral.random_password.langfuse_key["secret"].result}")
  })
  # Langfuse makes its project with them on its first start, and never again.
  secret_string_wo_version = 1
}

locals {
  # Each secret's ARN, once it is written, by its key: ECS injects it whole, or one of its JSON
  # keys as <arn>:<key>::.
  secret = merge(module.secrets.arns, {
    valkey        = aws_secretsmanager_secret_version.valkey.secret_arn
    langfuse-keys = aws_secretsmanager_secret_version.langfuse_keys.secret_arn
  })
  database = module.databases.arns
}
