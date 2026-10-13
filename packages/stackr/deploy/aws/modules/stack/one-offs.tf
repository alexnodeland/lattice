# The one-off tasks (RFC-0004): db-init, which creates each service's role and database; auth-keys,
# which writes GoTrue's key set and the service role's key when their secret is empty; and, with
# grantr, the application's db-roles, which creates the role it works as. Each runs by run-task,
# from the machine that applies, when its definition or the secrets it reads change, and the
# services that need it start after it (their `after`).

locals {
  one_off = {
    deployment         = var.name
    cluster_arn        = aws_ecs_cluster.this.arn
    subnet_ids         = module.network.private_subnet_ids
    security_group_ids = [module.network.security_groups.services]
    namespace_id       = aws_service_discovery_private_dns_namespace.this.id
  }
  # How run-task reaches the cluster, through the AWS CLI where OpenTofu runs.
  run_task = {
    CLUSTER        = aws_ecs_cluster.this.arn
    SUBNETS        = join(",", module.network.private_subnet_ids)
    SECURITY_GROUP = module.network.security_groups.services
    AWS_REGION     = local.region
  }
}

module "db_init" {
  source             = "../ecs-service"
  name               = "db-init"
  one_off            = true
  deployment         = local.one_off.deployment
  cluster_arn        = local.one_off.cluster_arn
  subnet_ids         = local.one_off.subnet_ids
  security_group_ids = local.one_off.security_group_ids
  namespace_id       = local.one_off.namespace_id
  size               = local.sizes["db-init"]
  log_retention_days = var.log_retention_days
  container = {
    image = var.images.db_init
    # RDS's master, named postgres, whose password RDS keeps.
    environment = {
      PGHOST            = module.data.postgres.address
      PGPORT            = tostring(module.data.postgres.port)
      PGDATABASE        = "postgres"
      PGUSER            = "postgres"
      PGSSLMODE         = local.postgres_tls
      PGCONNECT_TIMEOUT = "10"
      APP_DB_NAME       = local.app_database
    }
    secrets = {
      PGPASSWORD           = "${module.data.postgres.master_secret_arn}:password::"
      LANGFUSE_DB_PASSWORD = "${local.database["database-langfuse"]}:password::"
      LITELLM_DB_PASSWORD  = "${local.database["database-litellm"]}:password::"
      AUTH_DB_PASSWORD     = "${local.database["database-gotrue"]}:password::"
      GRAFANA_DB_PASSWORD  = "${local.database["database-grafana"]}:password::"
      APP_DB_PASSWORD      = "${local.database["database-app-owner"]}:password::"
    }
  }
}

resource "terraform_data" "db_init" {
  # Again when its definition changes, or a database's password is rotated.
  triggers_replace = [module.db_init.task_definition_arn, jsonencode(var.secret_versions)]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, { TASK_DEFINITION = module.db_init.task_definition_arn })
  }
}

module "auth_keys" {
  source             = "../ecs-service"
  name               = "auth-keys"
  one_off            = true
  deployment         = local.one_off.deployment
  cluster_arn        = local.one_off.cluster_arn
  subnet_ids         = local.one_off.subnet_ids
  security_group_ids = local.one_off.security_group_ids
  namespace_id       = local.one_off.namespace_id
  size               = local.sizes["auth-keys"]
  log_retention_days = var.log_retention_days
  container = {
    image       = var.images.auth_keys
    environment = merge(local.endpoint, { AUTH_KEYS_ARN = local.secret["auth-keys"], AWS_REGION = local.region })
  }
  # It reads its secret, and writes it when it is empty.
  task_role_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
      Resource = local.secret["auth-keys"]
    }]
  })
}

resource "terraform_data" "auth_keys" {
  triggers_replace = [module.auth_keys.task_definition_arn]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, { TASK_DEFINITION = module.auth_keys.task_definition_arn })
  }
}

module "db_roles" {
  source             = "../ecs-service"
  count              = local.grantr ? 1 : 0
  name               = "db-roles"
  one_off            = true
  deployment         = local.one_off.deployment
  cluster_arn        = local.one_off.cluster_arn
  subnet_ids         = local.one_off.subnet_ids
  security_group_ids = local.one_off.security_group_ids
  namespace_id       = local.one_off.namespace_id
  size               = local.sizes["db-roles"]
  log_retention_days = var.log_retention_days
  container = {
    image       = var.application.image
    command     = ["${var.application.name}-admin", "db-roles"]
    environment = local.app_environment
    secrets     = local.app_secrets
  }
}

resource "terraform_data" "db_roles" {
  count = local.grantr ? 1 : 0
  # Again when its definition changes, or its role's password is rotated; after db-init, which
  # creates the database and its owner.
  triggers_replace = [module.db_roles[0].task_definition_arn, lookup(var.secret_versions, "database-app", 1), terraform_data.db_init.id]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, { TASK_DEFINITION = module.db_roles[0].task_definition_arn })
  }
}
