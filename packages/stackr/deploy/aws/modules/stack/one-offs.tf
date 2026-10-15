# The one-off tasks (RFC-0004): db-init, which creates each service's role and database; auth-keys,
# which writes GoTrue's key set and the service role's key when each secret has none; and, with
# grantr, the application's db-roles, which creates the role it works as. Each runs by run-task,
# from the machine that applies: when its definition changes, and db-init and db-roles also when a
# database's password is rotated. The services that need a run wait for it (their `after`).

locals {
  # How run-task reaches the cluster, through the AWS CLI where OpenTofu runs, with the
  # provider's credentials when they aren't in that environment already.
  run_task = merge(var.run_task_environment, {
    CLUSTER    = aws_ecs_cluster.this.arn
    SUBNETS    = join(",", module.network.private_subnet_ids)
    AWS_REGION = local.region
  })
  # Each one-off task's log group, by its name: db-roles' only with grantr.
  one_off_logs = merge(
    { db-init = module.db_init.log_group_name, auth-keys = module.auth_keys.log_group_name },
    { for task in module.db_roles : "db-roles" => task.log_group_name },
  )
  # What run-task takes for each: its security groups, and where its container logs.
  one_off_environment = { for task, groups in local.groups_of : task => {
    SECURITY_GROUPS   = join(",", groups)
    LOG_GROUP         = local.one_off_logs[task]
    LOG_STREAM_PREFIX = "${task}/${task}"
  } if contains(keys(local.one_off_logs), task) }
  # The databases' versions, which db-init sets their roles' passwords from.
  database_versions = { for key, version in var.secret_versions : key => version if startswith(key, "database-") }
}

module "db_init" {
  source             = "../ecs-service"
  name               = "db-init"
  one_off            = true
  deployment         = local.task.deployment
  cluster_arn        = local.task.cluster_arn
  subnet_ids         = local.task.subnet_ids
  security_group_ids = local.groups_of["db-init"]
  size               = local.sizes["db-init"]
  log_retention_days = var.log_retention_days
  container = {
    image = var.images.db_init
    # RDS's master, named postgres, whose password RDS keeps.
    environment = merge({
      PGHOST            = module.data.postgres.address
      PGPORT            = tostring(module.data.postgres.port)
      PGDATABASE        = "postgres"
      PGUSER            = "postgres"
      PGSSLMODE         = local.postgres_tls
      PGCONNECT_TIMEOUT = "10"
      APP_DB_NAME       = local.app_database
      APP_DB_SCHEMA     = local.app_schema
    }, local.grantr ? { APP_DB_CREATES_ROLES = "true" } : {})
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
  triggers_replace = [module.db_init.task_definition_arn, jsonencode(local.database_versions)]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, local.one_off_environment["db-init"], { TASK_DEFINITION = module.db_init.task_definition_arn })
  }
  # Each run needs the private subnets' route out, to pull its image and read its secrets, and its
  # group's rule to PostgreSQL: with no rule, its group reaches nothing there.
  depends_on = [module.network, aws_vpc_security_group_ingress_rule.call, aws_vpc_security_group_egress_rule.call]
}

module "auth_keys" {
  source             = "../ecs-service"
  name               = "auth-keys"
  one_off            = true
  deployment         = local.task.deployment
  cluster_arn        = local.task.cluster_arn
  subnet_ids         = local.task.subnet_ids
  security_group_ids = local.groups_of["auth-keys"]
  size               = local.sizes["auth-keys"]
  log_retention_days = var.log_retention_days
  container = {
    image = var.images.auth_keys
    environment = merge(local.endpoint, {
      AUTH_JWT_KEYS_ARN         = local.secret["auth-jwt-keys"]
      AUTH_SERVICE_ROLE_KEY_ARN = local.secret["auth-service-role-key"]
      AWS_REGION                = local.region
    })
  }
  # It reads its two secrets, and writes each that has no value.
  task_role_policy_json = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:PutSecretValue"]
      Resource = [local.secret["auth-jwt-keys"], local.secret["auth-service-role-key"]]
    }]
  })
}

resource "terraform_data" "auth_keys" {
  triggers_replace = [module.auth_keys.task_definition_arn]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, local.one_off_environment["auth-keys"], { TASK_DEFINITION = module.auth_keys.task_definition_arn })
  }
  depends_on = [module.network]
}

# db-roles is the application's own admin command, with its two database URLs and the schema
# setting, if it gives one, and nothing else.
module "db_roles" {
  source             = "../ecs-service"
  count              = local.grantr ? 1 : 0
  name               = "db-roles"
  one_off            = true
  deployment         = local.task.deployment
  cluster_arn        = local.task.cluster_arn
  subnet_ids         = local.task.subnet_ids
  security_group_ids = local.groups_of["db-roles"]
  size               = local.sizes["db-roles"]
  log_retention_days = var.log_retention_days
  container = {
    image       = var.application.image
    command     = ["${var.application.name}-admin", "db-roles"]
    environment = { for key, value in var.application.environment : key => value if key == "DATABASE_SCHEMA" }
    secrets     = local.app_databases
  }
}

resource "terraform_data" "db_roles" {
  count = local.grantr ? 1 : 0
  # Again when its definition changes, or a password it sets or connects with is rotated; after
  # db-init, which creates the database and its owner.
  triggers_replace = [
    module.db_roles[0].task_definition_arn,
    jsonencode({ for key, version in local.database_versions : key => version if startswith(key, "database-app") }),
    terraform_data.db_init.id,
  ]

  provisioner "local-exec" {
    command     = "${path.module}/run-task"
    environment = merge(local.run_task, local.one_off_environment["db-roles"], { TASK_DEFINITION = module.db_roles[0].task_definition_arn })
  }
  depends_on = [module.network, aws_vpc_security_group_ingress_rule.call, aws_vpc_security_group_egress_rule.call]
}
