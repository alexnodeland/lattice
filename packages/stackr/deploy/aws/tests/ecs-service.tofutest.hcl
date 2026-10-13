# The ecs-service module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
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
    condition = toset(local.secret_arns) == toset([
      "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-master-key-AbCdEf",
      "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/litellm-database-AbCdEf",
    ])
    error_message = "The execution role reads each secret by its ARN, without a JSON key's suffix."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.secrets[0].policy).Statement[0].Action == "secretsmanager:GetSecretValue"
    error_message = "The execution role may only read the secrets."
  }
  assert {
    condition     = jsondecode(aws_iam_role.task.assume_role_policy).Statement[0].Condition.StringEquals["aws:SourceAccount"] == "000000000000"
    error_message = "Only this account's ECS tasks may take its roles."
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
