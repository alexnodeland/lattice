# stackr on AWS (RFC-0004): the network, the data stores, the edge, the cluster and its private
# namespace, the state host, every service on Fargate, and the one-off tasks that prepare them.
# envs/prod and envs/floci are its roots. The secrets are in secrets.tf, the services in
# services.tf, and the one-off tasks in one-offs.tf.

module "network" {
  source = "../network"
  name   = var.name
  cidr   = var.cidr
  zones  = var.zones
}

module "data" {
  source     = "../data"
  name       = var.name
  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.private_subnet_ids
  postgres = merge(var.postgres, {
    deletion_protection = !var.destroyable
    skip_final_snapshot = var.destroyable
  })
  valkey = merge(var.valkey, {
    auth_token_wo_version = lookup(var.secret_versions, "valkey", 1)
  })
  # The same token as Valkey's secret, from the same ephemeral password (secrets.tf).
  valkey_auth_token     = ephemeral.random_password.valkey.result
  force_destroy_buckets = var.destroyable

  clickhouse_backup_retention_days = var.clickhouse_backup_retention_days
}

module "edge" {
  source              = "../edge"
  name                = var.name
  domain              = var.domain
  zone_id             = var.zone_id
  vpc_id              = module.network.vpc_id
  subnet_ids          = module.network.public_subnet_ids
  public_subnet_cidrs = module.network.public_subnet_cidrs
  security_group_id   = module.network.security_groups.alb
  deletion_protection = !var.destroyable
  access_logs = {
    bucket = module.data.buckets["access-logs"].name
    prefix = module.data.access_logs_prefix
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

# The private namespace the services find each other in, as <service>.stackr.internal.
resource "aws_service_discovery_private_dns_namespace" "this" {
  name = local.namespace
  vpc  = module.network.vpc_id
}

module "state_host" {
  source                                = "../state-host"
  count                                 = var.state_host == "ec2" ? 1 : 0
  name                                  = var.name
  subnet_id                             = module.network.private_subnet_ids[0]
  private_ip                            = cidrhost(module.network.private_subnet_cidrs[0], 10)
  vpc_id                                = module.network.vpc_id
  namespace_id                          = aws_service_discovery_private_dns_namespace.this.id
  clickhouse_password_secret_arn        = module.secrets.arns["clickhouse-password"]
  clickhouse_admin_password_secret_arn  = module.secrets.arns["clickhouse-admin-password"]
  clickhouse_backup_password_secret_arn = module.secrets.arns["clickhouse-backup-password"]
  backups_bucket                        = module.data.buckets["backups"]
  lattice_commit                        = var.lattice_commit
  ami_id                                = var.ami_id
  instance_type                         = var.state_host_instance_type
  final_snapshot                        = !var.destroyable
}
