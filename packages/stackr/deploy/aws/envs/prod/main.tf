provider "aws" {
  region = var.region

  default_tags {
    tags = { Deployment = var.name, ManagedBy = "stackr" }
  }
}

module "stack" {
  source            = "../../modules/stack"
  name              = var.name
  domain            = var.domain
  zone_id           = var.zone_id
  zones             = var.zones
  ami_id            = var.ami_id
  lattice_commit    = var.lattice_commit
  images            = var.images
  application       = var.application
  gateway_providers = var.gateway_providers
  auth_smtp         = var.auth_smtp
  secret_versions   = var.secret_versions
}
