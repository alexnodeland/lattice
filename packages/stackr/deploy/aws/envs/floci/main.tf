locals {
  # Floci's account, and the keys it takes (any), which AWS doesn't.
  floci = {
    account    = "000000000000"
    access_key = "test"
    secret_key = "test"
  }
}

# Floci answers every service at AWS_ENDPOINT_URL, which the caller sets, and serves S3 by path.
provider "aws" {
  region              = "us-east-1"
  access_key          = local.floci.access_key
  secret_key          = local.floci.secret_key
  allowed_account_ids = [local.floci.account]
  s3_use_path_style   = true

  default_tags {
    tags = { Deployment = "stackr", ManagedBy = "stackr", Environment = "floci" }
  }
}

module "stack" {
  source             = "../../modules/stack"
  name               = "stackr"
  environment        = "floci"
  domain             = aws_route53_zone.this.name
  zone_id            = aws_route53_zone.this.zone_id
  zones              = ["us-east-1a", "us-east-1b"]
  images             = var.images
  application        = var.application
  state_host         = "fargate"
  tls_to_data        = false
  destroyable        = true
  aws_endpoint_url   = var.endpoint_for_tasks
  log_retention_days = 1
  # Valkey's port in Floci's proxy range (ADR-0025).
  valkey = { port = 6390 }
  # The one-off tasks' AWS CLI, with the same keys, at the same Floci.
  run_task_environment = {
    AWS_ACCESS_KEY_ID     = local.floci.access_key
    AWS_SECRET_ACCESS_KEY = local.floci.secret_key
    AWS_ENDPOINT_URL      = var.endpoint
  }
}

# The domain's zone, which Floci keeps: on AWS, an operator's.
resource "aws_route53_zone" "this" {
  name = "stackr.test"
}
