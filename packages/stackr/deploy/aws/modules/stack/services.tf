# Every service on Fargate (RFC-0004), each through ecs-service, with the settings compose.yaml
# gives it, its peers at their names in the namespace, and its secrets by reference. The thin
# images read their peers' names and their storage from the environment (ADR-0034).

locals {
  service = {
    deployment         = var.name
    cluster_arn        = aws_ecs_cluster.this.arn
    subnet_ids         = module.network.private_subnet_ids
    security_group_ids = [module.network.security_groups.services]
    namespace_id       = aws_service_discovery_private_dns_namespace.this.id
  }
  # The thin images' peers, at their names in the namespace; on one machine, Compose's names.
  peers = {
    TEMPO_ADDRESS      = local.address.tempo
    PROMETHEUS_ADDRESS = local.address.prometheus
    LOKI_ADDRESS       = local.address.loki
    PYROSCOPE_ADDRESS  = local.address.pyroscope
    LANGFUSE_ADDRESS   = local.address.langfuse-web
  }
  # Where AWS is, for a client that is told: only where it isn't AWS's own.
  endpoint = var.aws_endpoint_url == null ? {} : { AWS_ENDPOINT_URL = var.aws_endpoint_url }

  # What a service's task role may do in a bucket: under a prefix of it, or all of it.
  storage = {
    langfuse  = { bucket = module.data.buckets["langfuse"], prefix = "" }
    tempo     = { bucket = module.data.buckets["telemetry"], prefix = "tempo/" }
    loki      = { bucket = module.data.buckets["telemetry"], prefix = "loki/" }
    pyroscope = { bucket = module.data.buckets["telemetry"], prefix = "pyroscope/" }
  }
  storage_policy = { for service, storage in local.storage : service => jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = "s3:ListBucket"
        Resource  = storage.bucket.arn
        Condition = { StringLike = { "s3:prefix" = ["${storage.prefix}*"] } }
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${storage.bucket.arn}/${storage.prefix}*"
      },
    ]
  }) }
  # Tempo's, Loki's and Pyroscope's blocks, each under its own prefix of the telemetry bucket.
  telemetry_storage = { for service in ["tempo", "loki", "pyroscope"] : service => merge(local.endpoint, {
    S3_BUCKET = local.storage[service].bucket.name
    S3_REGION = local.region
    S3_PREFIX = local.storage[service].prefix
  }) }

  # Langfuse's web and worker share their settings, as in compose.yaml.
  langfuse_environment = merge(
    {
      # Operators reach Langfuse with SSM port forwarding, at localhost.
      NEXTAUTH_URL               = "http://localhost:3000"
      TELEMETRY_ENABLED          = "false"
      HOSTNAME                   = "0.0.0.0"
      CLICKHOUSE_URL             = "http://${local.address.clickhouse}:8123"
      CLICKHOUSE_MIGRATION_URL   = "clickhouse://${local.address.clickhouse}:9000"
      CLICKHOUSE_USER            = "langfuse"
      CLICKHOUSE_CLUSTER_ENABLED = "false"
    },
    merge([for upload, prefix in { EVENT = "events/", MEDIA = "media/" } : merge(
      {
        "LANGFUSE_S3_${upload}_UPLOAD_BUCKET"           = local.storage.langfuse.bucket.name
        "LANGFUSE_S3_${upload}_UPLOAD_PREFIX"           = prefix
        "LANGFUSE_S3_${upload}_UPLOAD_REGION"           = local.region
        "LANGFUSE_S3_${upload}_UPLOAD_FORCE_PATH_STYLE" = tostring(var.aws_endpoint_url != null)
      },
      var.aws_endpoint_url == null ? {} : { "LANGFUSE_S3_${upload}_UPLOAD_ENDPOINT" = var.aws_endpoint_url },
    )]...),
  )
  langfuse_secrets = {
    DATABASE_URL            = "${local.database["database-langfuse"]}:url::"
    SALT                    = local.secret["langfuse-salt"]
    ENCRYPTION_KEY          = local.secret["langfuse-encryption-key"]
    CLICKHOUSE_PASSWORD     = local.secret["clickhouse-password"]
    REDIS_CONNECTION_STRING = "${local.secret.valkey}:langfuse::"
  }
}

module "otel_collector" {
  source             = "../ecs-service"
  name               = "otel-collector"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes["otel-collector"]
  log_retention_days = var.log_retention_days
  container = {
    image = var.images.otel_collector
    port  = 4318
    environment = merge(local.peers, {
      STACKR_ENVIRONMENT      = var.environment
      STACKR_TRACES_EXPORTERS = "[otlp_grpc/tempo, otlp_http/langfuse]"
    })
    secrets = { LANGFUSE_OTLP_AUTH = "${local.secret["langfuse-keys"]}:otlp_auth::" }
  }
}

module "telemetry" {
  source             = "../ecs-service"
  for_each           = { tempo = 3200, loki = 3100, pyroscope = 4040 }
  name               = each.key
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes[each.key]
  log_retention_days = var.log_retention_days
  container = {
    image       = var.images[each.key]
    port        = each.value
    environment = merge(local.peers, local.telemetry_storage[each.key])
  }
  task_role_policy_json = local.storage_policy[each.key]
}

module "grafana" {
  source             = "../ecs-service"
  name               = "grafana"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes.grafana
  log_retention_days = var.log_retention_days
  container = {
    image = var.images.grafana
    port  = 3000
    # Its users and alert state on RDS, which db-init creates, so a replaced task keeps them.
    environment = merge(local.peers, {
      GF_SECURITY_ADMIN_USER = "admin"
      GF_DATABASE_TYPE       = "postgres"
      GF_DATABASE_HOST       = local.postgres
      GF_DATABASE_NAME       = "grafana"
      GF_DATABASE_USER       = "grafana"
      GF_DATABASE_SSL_MODE   = var.tls_to_data ? "require" : "disable"
    })
    secrets = {
      GF_SECURITY_ADMIN_PASSWORD = local.secret["grafana-admin-password"]
      GF_DATABASE_PASSWORD       = "${local.database["database-grafana"]}:password::"
    }
  }
  after = { db-init = terraform_data.db_init.id }
}

module "langfuse_web" {
  source             = "../ecs-service"
  name               = "langfuse-web"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes["langfuse-web"]
  log_retention_days = var.log_retention_days
  container = {
    image = local.upstream.langfuse_web
    port  = 3000
    # Its first start creates the organisation, the project with its keys, and the admin.
    environment = merge(local.langfuse_environment, {
      AUTH_DISABLE_SIGNUP        = "true"
      LANGFUSE_INIT_ORG_ID       = "stackr"
      LANGFUSE_INIT_ORG_NAME     = "stackr"
      LANGFUSE_INIT_PROJECT_ID   = "stackr"
      LANGFUSE_INIT_PROJECT_NAME = "stackr"
      LANGFUSE_INIT_USER_EMAIL   = coalesce(var.langfuse_admin_email, "admin@${var.domain}")
      LANGFUSE_INIT_USER_NAME    = "admin"
    })
    secrets = merge(local.langfuse_secrets, {
      NEXTAUTH_SECRET                  = local.secret["langfuse-nextauth-secret"]
      LANGFUSE_INIT_PROJECT_PUBLIC_KEY = "${local.secret["langfuse-keys"]}:public::"
      LANGFUSE_INIT_PROJECT_SECRET_KEY = "${local.secret["langfuse-keys"]}:secret::"
      LANGFUSE_INIT_USER_PASSWORD      = local.secret["langfuse-admin-password"]
    })
  }
  task_role_policy_json = local.storage_policy.langfuse
  after                 = { db-init = terraform_data.db_init.id }
}

module "langfuse_worker" {
  source             = "../ecs-service"
  name               = "langfuse-worker"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes["langfuse-worker"]
  log_retention_days = var.log_retention_days
  container = {
    image       = local.upstream.langfuse_worker
    port        = 3030
    environment = local.langfuse_environment
    secrets     = local.langfuse_secrets
  }
  task_role_policy_json = local.storage_policy.langfuse
  after                 = { db-init = terraform_data.db_init.id }
}

module "litellm" {
  source             = "../ecs-service"
  name               = "litellm"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes.litellm
  log_retention_days = var.log_retention_days
  container = {
    image   = var.images.litellm
    port    = 4000
    command = ["--config", "/etc/litellm/config.yaml", "--port", "4000"]
    environment = {
      LITELLM_OTEL_V2                         = "true"
      OTEL_EXPORTER_OTLP_ENDPOINT             = local.otlp
      OTEL_EXPORTER_OTLP_PROTOCOL             = "http/protobuf"
      OTEL_SERVICE_NAME                       = "litellm"
      OTEL_RESOURCE_ATTRIBUTES                = "deployment.environment.name=${var.environment}"
      LITELLM_OTEL_INTEGRATION_ENABLE_METRICS = "true"
      LITELLM_LOCAL_MODEL_COST_MAP            = "True"
      LITELLM_MODE                            = "PRODUCTION"
    }
    secrets = merge(
      {
        LITELLM_MASTER_KEY = local.secret["litellm-master-key"]
        LITELLM_SALT_KEY   = local.secret["litellm-salt-key"]
        DATABASE_URL       = "${local.database["database-litellm"]}:url::"
        REDIS_URL          = "${local.secret.valkey}:litellm::"
      },
      { for provider in var.gateway_providers : "${upper(provider)}_API_KEY" => local.secret["litellm-${provider}-api-key"] },
    )
  }
  after = { db-init = terraform_data.db_init.id }
}

# GoTrue, behind its proxy in its task (ADR-0032): the proxy takes its port and the edge's target
# group, and GoTrue listens on the task's loopback, keying its rate limits on the one address the
# proxy passes it.
module "gotrue" {
  source             = "../ecs-service"
  name               = "gotrue"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes.gotrue
  log_retention_days = var.log_retention_days
  target_group_arn   = module.edge.target_groups.auth
  proxy              = { image = module.edge.auth_proxy.image, caddyfile = module.edge.auth_proxy.caddyfile }
  container = {
    image = local.upstream.gotrue
    port  = 9999
    environment = merge(
      {
        GOTRUE_API_HOST               = "127.0.0.1"
        PORT                          = tostring(module.edge.auth_proxy.gotrue_port)
        API_EXTERNAL_URL              = "https://${local.hosts.auth}"
        GOTRUE_SITE_URL               = "https://${local.hosts.app}"
        GOTRUE_DB_DRIVER              = "postgres"
        GOTRUE_JWT_ISSUER             = "https://${local.hosts.auth}"
        GOTRUE_JWT_AUD                = "authenticated"
        GOTRUE_JWT_DEFAULT_GROUP_NAME = "authenticated"
        GOTRUE_JWT_ADMIN_ROLES        = "service_role"
        GOTRUE_JWT_EXP                = "3600"
        GOTRUE_EXTERNAL_EMAIL_ENABLED = "true"
        GOTRUE_DISABLE_SIGNUP         = "true"
        GOTRUE_RATE_LIMIT_HEADER      = "X-Forwarded-For"
      },
      var.auth_smtp == null ? {} : {
        GOTRUE_SMTP_HOST        = var.auth_smtp.host
        GOTRUE_SMTP_PORT        = tostring(var.auth_smtp.port)
        GOTRUE_SMTP_USER        = var.auth_smtp.user
        GOTRUE_SMTP_ADMIN_EMAIL = var.auth_smtp.sender
      },
    )
    secrets = merge(
      {
        GOTRUE_DB_DATABASE_URL = "${local.database["database-gotrue"]}:url::"
        GOTRUE_JWT_KEYS        = "${local.secret["auth-keys"]}:jwt_keys::"
        GOTRUE_JWT_SECRET      = local.secret["gotrue-jwt-secret"]
      },
      var.auth_smtp == null ? {} : { GOTRUE_SMTP_PASS = local.secret["auth-smtp-password"] },
    )
  }
  after = { db-init = terraform_data.db_init.id, auth-keys = terraform_data.auth_keys.id }
}

# The application, at app.<domain>: the settings the stack gives it, then its own.
locals {
  app_environment = merge(
    {
      APP_HOST                    = "0.0.0.0"
      APP_PORT                    = "8000"
      APP_ENVIRONMENT             = var.environment
      OTEL_EXPORTER_OTLP_ENDPOINT = local.otlp
      OTEL_SERVICE_NAME           = var.application.name
      LANGFUSE_BASE_URL           = "http://${local.address.langfuse-web}:3000"
      LITELLM_BASE_URL            = "http://${local.address.litellm}:4000"
      AUTH_ISSUER                 = "https://${local.hosts.auth}"
      AUTH_AUDIENCE               = "authenticated"
      # GoTrue's key set and admin API, at its private address: the edge refuses /admin.
      AUTH_JWKS_URL = "http://${local.address.gotrue}:9999/.well-known/jwks.json"
    },
    local.grantr ? { AUTH_ADMIN_URL = "http://${local.address.gotrue}:9999" } : {},
    var.application.environment,
  )
  app_secrets = merge(
    {
      LANGFUSE_PUBLIC_KEY = "${local.secret["langfuse-keys"]}:public::"
      LANGFUSE_SECRET_KEY = "${local.secret["langfuse-keys"]}:secret::"
    },
    # With grantr, it works as a role that owns nothing, and migrates as the owner (ADR-0022).
    local.grantr ? {
      DATABASE_URL          = "${local.database["database-app"]}:url::"
      DATABASE_ADMIN_URL    = "${local.database["database-app-owner"]}:url::"
      AUTH_SERVICE_ROLE_KEY = "${local.secret["auth-keys"]}:service_role_key::"
      } : {
      DATABASE_URL = "${local.database["database-app-owner"]}:url::"
    },
    var.application.secrets,
  )
}

module "app" {
  source             = "../ecs-service"
  name               = "app"
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes.app
  log_retention_days = var.log_retention_days
  target_group_arn   = module.edge.target_groups.app
  container = {
    image       = var.application.image
    port        = 8000
    environment = local.app_environment
    secrets     = local.app_secrets
  }
  after = merge({ db-init = terraform_data.db_init.id }, { for run in terraform_data.db_roles : "db-roles" => run.id })
}
