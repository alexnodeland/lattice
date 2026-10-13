# One Fargate service (RFC-0004): its task definition, with its secrets injected from Secrets
# Manager by ARN and never in the definition; its logs; its name in the private namespace; and its
# target group, when the edge reaches it. A one-off task, such as db-init, is its definition alone,
# which the recipe runs by run-task.

locals {
  family = "${var.deployment}-${var.name}"
  # The secrets the execution role may read: each ARN, without a JSON key's suffix.
  secret_arns = distinct([
    for value in values(var.container.secrets) : regex("^(arn:[^:]+:secretsmanager:[^:]+:[^:]+:secret:[^:]+)", value)[0]
  ])
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/${var.deployment}/${var.name}"
  retention_in_days = var.log_retention_days
}

data "aws_caller_identity" "current" {}

# ECS's tasks in this account only may take its roles, against the confused deputy.
locals {
  assume = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:*" }
      }
    }]
  })
}

# The execution role: pulls the image, writes the logs, and reads the secrets.
resource "aws_iam_role" "execution" {
  name               = "${local.family}-execution"
  assume_role_policy = local.assume
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role_policy" "secrets" {
  count = length(local.secret_arns) > 0 ? 1 : 0
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

  container_definitions = jsonencode([{
    name         = var.name
    image        = var.container.image
    essential    = true
    command      = var.container.command
    portMappings = var.container.port == null ? [] : [{ containerPort = var.container.port, protocol = "tcp" }]
    environment  = [for key, value in var.container.environment : { name = key, value = value }]
    secrets      = [for key, value in var.container.secrets : { name = key, valueFrom = value }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = var.name
      }
    }
  }])
}

data "aws_region" "current" {}

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
      container_name   = var.name
      container_port   = var.container.port
    }
  }
}
