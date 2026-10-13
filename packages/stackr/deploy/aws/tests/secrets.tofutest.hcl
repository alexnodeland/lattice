# The secrets module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {}

variables {
  name = "stackr"
  generated = {
    redis-auth-token = {}
    litellm-master-key = {
      template = "sk-{password}"
    }
    langfuse-encryption-key = {
      template = "{password_sha256}"
    }
    litellm-database = {
      keys = {
        password = "{password}"
        url      = "postgresql://litellm:{password}@db:5432/litellm?sslmode=require"
      }
    }
  }
  written_elsewhere = ["anthropic-api-key"]
}

run "secrets_named_by_the_deployment" {
  command = plan
  module {
    source = "./modules/secrets"
  }

  assert {
    condition     = aws_secretsmanager_secret.generated["litellm-database"].name == "stackr/litellm-database"
    error_message = "Each secret is <name>/<key>."
  }
  assert {
    condition     = length(aws_secretsmanager_secret.written_elsewhere) == 1
    error_message = "A secret written elsewhere is made empty."
  }
  assert {
    condition     = alltrue([for secret in aws_secretsmanager_secret.generated : secret.recovery_window_in_days == 30])
    error_message = "A deleted secret can be restored for 30 days by default."
  }
}

run "secrets_a_generated_secret_never_reaches_state" {
  command = plan
  module {
    source = "./modules/secrets"
  }

  assert {
    condition = alltrue([
      for version in aws_secretsmanager_secret_version.generated :
      version.secret_string == null && version.secret_string_wo_version == 1
    ])
    error_message = "Generated secrets go through secret_string_wo, written once."
  }
}

run "secrets_refuse_a_recovery_window_secrets_manager_doesnt_take" {
  command = plan
  module {
    source = "./modules/secrets"
  }
  variables {
    recovery_window_in_days = 3
  }
  expect_failures = [var.recovery_window_in_days]
}

run "secrets_refuse_a_short_password" {
  command = plan
  module {
    source = "./modules/secrets"
  }
  variables {
    generated = { short = { length = 8 } }
  }
  expect_failures = [var.generated]
}

run "secrets_refuse_a_template_without_the_password" {
  command = plan
  module {
    source = "./modules/secrets"
  }
  variables {
    generated = { constant = { keys = { url = "postgresql://db:5432/x" } } }
  }
  expect_failures = [var.generated]
}

run "secrets_refuse_a_template_with_keys" {
  command = plan
  module {
    source = "./modules/secrets"
  }
  variables {
    generated = { both = { template = "sk-{password}", keys = { key = "{password}" } } }
  }
  expect_failures = [var.generated]
}
