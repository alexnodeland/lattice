# The provider applies only to the account the deployment names, with the credentials of its
# profile, or of the shell when it names none. The one-off tasks run with the same profile.
provider "aws" {
  region              = var.region
  profile             = var.profile
  allowed_account_ids = [var.account_id]

  default_tags {
    tags = { Deployment = var.name, ManagedBy = "stackr" }
  }
}

module "stack" {
  source               = "../../modules/stack"
  name                 = var.name
  domain               = var.domain
  zone_id              = var.zone_id
  zones                = var.zones
  ami_id               = var.ami_id
  lattice_commit       = var.lattice_commit
  images               = var.images
  application          = var.application
  gateway_providers    = var.gateway_providers
  auth_smtp            = var.auth_smtp
  secret_versions      = var.secret_versions
  langfuse_admin_email = var.langfuse_admin_email

  clickhouse_backup_retention_days = var.clickhouse_backup_retention_days
  run_task_environment             = var.profile == null ? {} : { AWS_PROFILE = var.profile }
}
