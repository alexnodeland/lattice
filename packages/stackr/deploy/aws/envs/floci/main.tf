locals {
  # Floci's account, and the keys it takes (any), which AWS doesn't.
  floci = {
    account    = "000000000000"
    access_key = "test"
    secret_key = "test"
  }
}

# Floci answers every service the stack uses at var.endpoint, which its validation keeps on the
# loopback, named here for each: an endpoint here wins over any AWS_ENDPOINT_URL_* in the caller's
# environment, and the static keys over any profile, so neither reaches AWS. It serves S3 by path.
provider "aws" {
  region              = "us-east-1"
  access_key          = local.floci.access_key
  secret_key          = local.floci.secret_key
  allowed_account_ids = [local.floci.account]
  s3_use_path_style   = true
  # Floci answers at once, or not at all: a few retries, not AWS's many.
  max_retries = 3

  endpoints {
    acm              = var.endpoint
    cloudwatch       = var.endpoint
    cloudwatchlogs   = var.endpoint
    dlm              = var.endpoint
    ec2              = var.endpoint
    ecs              = var.endpoint
    elasticache      = var.endpoint
    elbv2            = var.endpoint
    iam              = var.endpoint
    rds              = var.endpoint
    route53          = var.endpoint
    s3               = var.endpoint
    s3control        = var.endpoint
    secretsmanager   = var.endpoint
    servicediscovery = var.endpoint
    sts              = var.endpoint
  }

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
  # The one-off tasks' AWS CLI, with the same keys, at the same Floci, for each service it calls,
  # and with no configuration of the caller's, so a hand-run apply can't reach AWS either.
  run_task_environment = {
    AWS_ACCESS_KEY_ID                = local.floci.access_key
    AWS_SECRET_ACCESS_KEY            = local.floci.secret_key
    AWS_ENDPOINT_URL                 = var.endpoint
    AWS_ENDPOINT_URL_ECS             = var.endpoint
    AWS_ENDPOINT_URL_CLOUDWATCH_LOGS = var.endpoint
    AWS_CONFIG_FILE                  = "/dev/null"
    AWS_SHARED_CREDENTIALS_FILE      = "/dev/null"
  }
}

# The domain's zone, which Floci keeps: on AWS, an operator's.
resource "aws_route53_zone" "this" {
  name = "stackr.test"
}
