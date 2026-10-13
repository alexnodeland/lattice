# The ecs-service module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:000000000000:log-group:/stackr/litellm" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mocked" }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = { arn = "arn:aws:servicediscovery:us-east-1:000000000000:service/srv-mocked" }
  }
}

variables {
  name               = "litellm"
  deployment         = "stackr"
  cluster_arn        = "arn:aws:ecs:us-east-1:000000000000:cluster/stackr"
  subnet_ids         = ["subnet-a", "subnet-b"]
  security_group_ids = ["sg-services"]
  namespace_id       = "ns-mocked"
  container = {
    image       = "ghcr.io/alexnodeland/stackr-litellm@sha256:0000000000000000000000000000000000000000000000000000000000000000"
    port        = 4000
    environment = { REDIS_HOST = "valkey" }
    secrets = {
      LITELLM_MASTER_KEY = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-master-key-AbCdEf"
      DATABASE_URL       = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-database-AbCdEf:url::"
    }
  }
}

run "ecs_service_secrets_come_from_secrets_manager_never_the_definition" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }

  assert {
    condition = (
      jsondecode(aws_ecs_task_definition.this.container_definitions)[0].environment == [{ name = "REDIS_HOST", value = "valkey" }]
      && length(jsondecode(aws_ecs_task_definition.this.container_definitions)[0].secrets) == 2
    )
    error_message = "Settings are environment; secrets are references to Secrets Manager."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.secrets[0].policy).Statement == [{
      Effect = "Allow"
      Action = "secretsmanager:GetSecretValue"
      Resource = [
        "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-database-AbCdEf",
        "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-master-key-AbCdEf",
      ]
    }]
    error_message = "The execution role may read exactly its secrets, each by its ARN without a JSON key's suffix."
  }
  assert {
    condition = jsondecode(aws_iam_role_policy.execution.policy).Statement == [{
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = "arn:aws:logs:us-east-1:000000000000:log-group:/stackr/litellm:*"
    }]
    error_message = "Otherwise, the execution role may only write to its own log group: no ECR without a repository."
  }
  assert {
    condition = alltrue([
      for role in [aws_iam_role.task, aws_iam_role.execution] :
      jsondecode(role.assume_role_policy).Statement[0].Principal.Service == "ecs-tasks.amazonaws.com"
      && jsondecode(role.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "000000000000"
      && jsondecode(role.assume_role_policy).Statement[0].Condition.ArnLike["aws:SourceArn"] == "arn:aws:ecs:us-east-1:000000000000:*"
    ])
    error_message = "Only this account's ECS tasks, in this region, may take either role."
  }
  assert {
    condition     = aws_ecs_service.this[0].network_configuration[0].assign_public_ip == false && aws_ecs_service.this[0].deployment_circuit_breaker[0].rollback
    error_message = "Tasks have no public address, and a failed deployment rolls back."
  }
}

run "ecs_service_a_one_off_is_a_definition_alone" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    one_off = true
  }

  assert {
    condition     = length(aws_ecs_service.this) == 0 && length(aws_service_discovery_service.this) == 0
    error_message = "A one-off task has no service and no name."
  }
}

run "ecs_service_a_secret_is_an_arn" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    container = {
      image   = "stackr-litellm"
      secrets = { LITELLM_MASTER_KEY = "sk-plain-text" }
    }
  }
  expect_failures = [var.container]
}

run "ecs_service_a_setting_is_never_both" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    container = {
      image       = "stackr-litellm"
      environment = { DATABASE_URL = "postgresql://plain" }
      secrets     = { DATABASE_URL = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/x-AbCdEf" }
    }
  }
  expect_failures = [var.container]
}

run "ecs_service_pulls_from_ecr_only_the_repositories_it_is_given" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    ecr_repository_arns = ["arn:aws:ecr:us-east-1:000000000000:repository/app"]
  }

  assert {
    condition = (
      jsondecode(aws_iam_role_policy.execution.policy).Statement[2].Resource == ["arn:aws:ecr:us-east-1:000000000000:repository/app"]
      && length(jsondecode(aws_iam_role_policy.execution.policy).Statement) == 3
    )
    error_message = "The execution role pulls from the repositories it is given, and no others."
  }
}

run "ecs_service_counts_its_policies_before_their_arns_are_known" {
  command = plan
  module {
    source = "./tests/fixtures/unknown-arns"
  }

  assert {
    condition     = length(module.service.task_definition_arn) > 0
    error_message = "A service whose secrets' and bucket's ARNs are unknown at plan still plans."
  }
}

run "ecs_service_a_proxy_takes_the_port_and_the_target_group" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/stackr-auth/mocked"
    proxy = {
      image     = "caddy:2"
      caddyfile = ":4000 {\n}\n"
    }
  }

  assert {
    condition = (
      [for container in jsondecode(aws_ecs_task_definition.this.container_definitions) : container.name] == ["litellm", "proxy"]
      && jsondecode(aws_ecs_task_definition.this.container_definitions)[0].portMappings == []
      && jsondecode(aws_ecs_task_definition.this.container_definitions)[1].portMappings == [{ containerPort = 4000, protocol = "tcp" }]
    )
    error_message = "The proxy takes the service's port; the service has none outside its task."
  }
  assert {
    condition     = jsondecode(aws_ecs_task_definition.this.container_definitions)[1].environment == [{ name = "CADDYFILE", value = ":4000 {\n}\n" }]
    error_message = "The proxy's configuration comes from its environment."
  }
  assert {
    condition     = one(aws_ecs_service.this[0].load_balancer).container_name == "proxy" && one(aws_ecs_service.this[0].load_balancer).container_port == 4000
    error_message = "The target group reaches the proxy."
  }
}

run "ecs_service_a_target_group_needs_a_service" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    one_off          = true
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/stackr-app/mocked"
  }
  expect_failures = [var.target_group_arn]
}

run "ecs_service_a_proxy_needs_a_port" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    container = { image = "stackr-litellm" }
    proxy     = { image = "caddy:2", caddyfile = "" }
  }
  expect_failures = [var.proxy]
}

run "ecs_service_starts_again_after_the_runs_it_waits_for" {
  command = plan
  module {
    source = "./modules/ecs-service"
  }
  variables {
    after = { db-init = "run-1" }
  }

  assert {
    condition     = aws_ecs_service.this[0].triggers == { db-init = "run-1" }
    error_message = "A new run of a one-off it waits for deploys the service again."
  }
}
