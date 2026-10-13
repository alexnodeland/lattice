# One Fargate service (RFC-0004): its task definition, with its secrets injected from Secrets
# Manager by ARN and never in the definition; its logs; its name in the private namespace; and its
# target group, when the edge reaches it. A one-off task, such as db-init, is its definition alone,
# which the recipe runs by run-task. A service may have a proxy in front of it, in its task, such as
# GoTrue's: the proxy then takes the service's port, and the service listens on the task's loopback.
# A service may also wait, in its task, for a container that must end well first.

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

locals {
  family    = "${var.deployment}-${var.name}"
  account   = data.aws_caller_identity.current.account_id
  partition = data.aws_partition.current.partition
  region    = data.aws_region.current.region
  # The secrets the execution role may read: each ARN, without a JSON key's suffix.
  secret_arns = distinct([
    for value in values(var.container.secrets) : regex("^(arn:[^:]+:secretsmanager:[^:]+:[^:]+:secret:[^:]+)", value)[0]
  ])
  # The container the edge and the other services reach: the proxy, when there is one.
  front = var.proxy == null ? var.name : "proxy"

  # ECS's tasks in this account only may take its roles, against the confused deputy.
  assume = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account }
        ArnLike      = { "aws:SourceArn" = "arn:${local.partition}:ecs:${local.region}:${local.account}:*" }
      }
    }]
  })

  logs = {
    logDriver = "awslogs"
    options = {
      awslogs-group         = aws_cloudwatch_log_group.this.name
      awslogs-region        = local.region
      awslogs-stream-prefix = var.name
    }
  }
  main = {
    name                   = var.name
    image                  = var.container.image
    essential              = true
    command                = var.container.command
    portMappings           = var.container.port == null || var.proxy != null ? [] : [{ containerPort = var.container.port, protocol = "tcp" }]
    environment            = [for key, value in var.container.environment : { name = key, value = value }]
    secrets                = [for key, value in var.container.secrets : { name = key, valueFrom = value }]
    readonlyRootFilesystem = var.container.readonly_root_filesystem
    logConfiguration       = local.logs
  }
  # With a wait, the service's container starts only once the wait has exited 0. ECS's startTimeout
  # is left unset: Fargate caps it at 120 seconds, and the wait bounds itself.
  service = merge(local.main, var.wait == null ? {} : { dependsOn = [{ containerName = "wait", condition = "SUCCESS" }] })
  # A container that must end well before the service's starts, such as one that waits for
  # another service to be ready.
  wait = var.wait == null ? [] : [{
    name                   = "wait"
    image                  = var.wait.image
    essential              = false
    command                = var.wait.command
    readonlyRootFilesystem = true
    logConfiguration = merge(local.logs, {
      options = merge(local.logs.options, { awslogs-stream-prefix = "${var.name}-wait" })
    })
  }]
  # Caddy, with its configuration from the environment: it needs no image of its own.
  proxy = var.proxy == null ? [] : [{
    name         = "proxy"
    image        = var.proxy.image
    essential    = true
    entryPoint   = ["sh", "-c"]
    command      = ["printf '%s' \"$CADDYFILE\" >/tmp/Caddyfile && exec caddy run --config /tmp/Caddyfile --adapter caddyfile"]
    portMappings = [{ containerPort = var.container.port, protocol = "tcp" }]
    environment  = [{ name = "CADDYFILE", value = var.proxy.caddyfile }]
    dependsOn    = [{ containerName = var.name, condition = "START" }]
    logConfiguration = merge(local.logs, {
      options = merge(local.logs.options, { awslogs-stream-prefix = "${var.name}-proxy" })
    })
  }]
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/${var.deployment}/${var.name}"
  retention_in_days = var.log_retention_days
}

# The execution role: writes the logs, pulls from ECR only when given a repository, and reads the
# secrets; nothing more.
resource "aws_iam_role" "execution" {
  name               = "${local.family}-execution"
  assume_role_policy = local.assume
}

resource "aws_iam_role_policy" "execution" {
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      [{
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.this.arn}:*"
      }],
      # The images are public, on GHCR and Docker Hub, which need no role.
      length(var.ecr_repository_arns) == 0 ? [] : [
        { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = ["*"] },
        {
          Effect   = "Allow"
          Action   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
          Resource = var.ecr_repository_arns
        },
      ],
    )
  })
}

# Counted by the secrets' names, which are known at plan; their ARNs are often another module's
# outputs, which aren't.
resource "aws_iam_role_policy" "secrets" {
  count = length(var.container.secrets) > 0 ? 1 : 0
  role  = aws_iam_role.execution.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = local.secret_arns }]
  })
}

# The task role: what the service itself may do in AWS.
resource "aws_iam_role" "task" {
  name               = "${local.family}-task"
  assume_role_policy = local.assume
}

resource "aws_iam_role_policy" "task" {
  count  = var.task_role_policy_json == null ? 0 : 1
  role   = aws_iam_role.task.id
  policy = var.task_role_policy_json
}

resource "aws_ecs_task_definition" "this" {
  family                   = local.family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.size.cpu
  memory                   = var.size.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }

  container_definitions = jsonencode(concat([local.service], local.proxy, local.wait))
}

resource "aws_service_discovery_service" "this" {
  count = var.one_off ? 0 : 1
  name  = var.name

  dns_config {
    namespace_id = var.namespace_id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
}

resource "aws_ecs_service" "this" {
  count                  = var.one_off ? 0 : 1
  name                   = var.name
  cluster                = var.cluster_arn
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"
  # Created after each one-off run and secret version it waits for, and deployed again, with new
  # tasks, when one changes: a trigger alone updates the service in place and keeps its tasks.
  triggers             = var.after
  force_new_deployment = length(var.after) > 0

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  service_registries {
    registry_arn = aws_service_discovery_service.this[0].arn
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn == null ? [] : [var.target_group_arn]
    content {
      target_group_arn = load_balancer.value
      container_name   = local.front
      container_port   = var.container.port
    }
  }
}
