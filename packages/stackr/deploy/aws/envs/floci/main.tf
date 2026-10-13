# Floci answers every service at AWS_ENDPOINT_URL, with its own credentials, which the caller sets
# (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY), and serves S3 by path.
provider "aws" {
  region                      = "us-east-1"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  s3_use_path_style           = true
}

module "stack" {
  source             = "../../modules/stack"
  name               = "stackr"
  environment        = "floci"
  domain             = "stackr.test"
  zone_id            = aws_route53_zone.this.zone_id
  zones              = ["us-east-1a", "us-east-1b"]
  images             = var.images
  application        = var.application
  state_host         = "fargate"
  tls_to_data        = false
  destroyable        = true
  aws_endpoint_url   = var.endpoint_for_tasks
  log_retention_days = 1

  # Floci's catalog has nothing above medium (ADR-0025).
  postgres = { instance_class = "db.t4g.micro", allocated_storage = 20, max_allocated_storage = 20, backup_retention_days = 1 }
  valkey   = { node_type = "cache.t4g.micro", port = 6390 }
  sizes = { for service in ["app", "litellm", "langfuse-web", "langfuse-worker", "clickhouse"] :
    service => { cpu = 512, memory = 1024 }
  }
}

# The domain's zone, which Floci keeps: on AWS, an operator's.
resource "aws_route53_zone" "this" {
  name = "stackr.test"
}
