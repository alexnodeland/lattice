# A service whose secrets' and bucket's ARNs aren't known until apply, as when they are the secrets
# and data modules' outputs: random_id's hex is unknown at plan, even against a mocked AWS
# (tests/ecs-service).
terraform {
  required_version = ">= 1.13"
  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.8"
    }
  }
}

resource "random_id" "this" {
  byte_length = 3
}

module "service" {
  source             = "../../../modules/ecs-service"
  name               = "litellm"
  deployment         = "stackr"
  cluster_arn        = "arn:aws:ecs:us-east-1:000000000000:cluster/stackr"
  subnet_ids         = ["subnet-a"]
  security_group_ids = ["sg-services"]
  namespace_id       = "ns-mocked"
  container = {
    image   = "stackr-litellm"
    port    = 4000
    secrets = { LITELLM_MASTER_KEY = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/x-${random_id.this.hex}" }
  }
  task_role_policy_json = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "s3:GetObject", Resource = "arn:aws:s3:::stackr-${random_id.this.hex}/*" }]
  })
}
