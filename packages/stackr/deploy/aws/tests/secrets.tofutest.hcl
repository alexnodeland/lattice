# The secrets module, planned against a mocked AWS (tier 1, RFC-0004).

mock_provider "aws" {}

variables {
  name = "stackr"
  generated = {
    redis-auth-token = {}
    litellm-database = {
      keys = {
        password = "{password}"
        url      = "postgresql://litellm:{password}@db:5432/litellm?sslmode=require"
      }
    }
  }
  written_elsewhere = ["anthropic-api-key"]
}

run "secrets_named_named_by_the_deployment" {
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
