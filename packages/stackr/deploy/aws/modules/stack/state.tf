# ClickHouse, Prometheus and prom-label-proxy as Fargate services, without a volume, where the state
# host can't run: Floci (ADR-0025). The state host is main.tf's. Without its checkout, ClickHouse
# has no users.xml: its image makes Langfuse's user alone, with no admin (ADR-0034), and Prometheus
# scrapes only itself, taking its metrics by OTLP and remote write as on the state host.

locals {
  fargate_state = { for name, service in {
    clickhouse = {
      image   = local.upstream.clickhouse
      port    = 8123
      command = null
      environment = {
        CLICKHOUSE_USER                      = "langfuse"
        CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT = "1"
      }
      secrets = { CLICKHOUSE_PASSWORD = local.secret["clickhouse-password"] }
    }
    prometheus = {
      image = local.upstream.prometheus
      port  = 9090
      command = [
        "--config.file=/etc/prometheus/prometheus.yml",
        "--storage.tsdb.path=/prometheus",
        "--storage.tsdb.retention.time=15d",
        "--web.enable-otlp-receiver",
        "--web.enable-remote-write-receiver",
        "--enable-feature=exemplar-storage",
      ]
      environment = {}
      secrets     = {}
    }
    prom-label-proxy = {
      image = local.upstream.prom_label_proxy
      port  = 9091
      command = [
        "-label=tenant_id",
        "-upstream=http://${local.address.prometheus}:9090",
        "-insecure-listen-address=0.0.0.0:9091",
        "-internal-listen-address=127.0.0.1:8081",
      ]
      environment = {}
      secrets     = {}
    }
  } : name => service if var.state_host == "fargate" }
}

module "state_services" {
  source             = "../ecs-service"
  for_each           = local.fargate_state
  name               = each.key
  deployment         = local.service.deployment
  cluster_arn        = local.service.cluster_arn
  subnet_ids         = local.service.subnet_ids
  security_group_ids = local.service.security_group_ids
  namespace_id       = local.service.namespace_id
  size               = local.sizes[each.key]
  log_retention_days = var.log_retention_days
  container = {
    image       = each.value.image
    port        = each.value.port
    command     = each.value.command
    environment = each.value.environment
    secrets     = each.value.secrets
  }
}
