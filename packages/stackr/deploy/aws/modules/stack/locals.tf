# The images stackr runs as they are, pinned as compose.yaml pins them, which scripts/check-config
# holds them to; each service's size; and where each service is, by its name in the namespace.

data "aws_region" "current" {}

locals {
  upstream = {
    gotrue           = "supabase/gotrue:v2.197.0@sha256:1736a63078f5922b198c4cbe50f80ab9a2d3b54fe8b7b6cfb2e9dc5dbbc12c6b"
    langfuse_web     = "langfuse/langfuse:4.46.0@sha256:755b821ba8f73a20d43d90e68f2b75d2f597dd164c55890f67a05f5a8d0f0e24"
    langfuse_worker  = "langfuse/langfuse-worker:4.46.0@sha256:3568d2d1eb5dd570f4087b37972ddffa3f6ae4f872553e0b0e2eedf4896a29e9"
    clickhouse       = "clickhouse/clickhouse-server:26.9.3.38@sha256:12b16e744f91d8228705e136bd2b0ab14c939c87ff82443090279b65255c50c1"
    prometheus       = "prom/prometheus:v3.15.0@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e"
    prom_label_proxy = "quay.io/prometheuscommunity/prom-label-proxy:v0.15.1@sha256:186f9fe791158ef25d6f810109746ac0acdb35cb8401b554526c77c065483373"
  }

  sizes = merge({
    app              = { cpu = 512, memory = 1024 }
    gotrue           = { cpu = 256, memory = 512 }
    litellm          = { cpu = 1024, memory = 2048 }
    langfuse-web     = { cpu = 1024, memory = 2048 }
    langfuse-worker  = { cpu = 1024, memory = 2048 }
    otel-collector   = { cpu = 512, memory = 1024 }
    tempo            = { cpu = 512, memory = 1024 }
    loki             = { cpu = 512, memory = 1024 }
    pyroscope        = { cpu = 512, memory = 1024 }
    grafana          = { cpu = 256, memory = 512 }
    clickhouse       = { cpu = 1024, memory = 4096 }
    prometheus       = { cpu = 512, memory = 1024 }
    prom-label-proxy = { cpu = 256, memory = 512 }
    db-init          = { cpu = 256, memory = 512 }
    auth-keys        = { cpu = 256, memory = 512 }
    db-roles         = { cpu = 256, memory = 512 }
  }, var.sizes)

  region    = data.aws_region.current.region
  namespace = "stackr.internal"
  grantr    = var.application.access == "grantr"

  # Each service's name, as the others reach it; the thin images read their peers' from the
  # environment, by these names (ADR-0034).
  address = { for service in ["otel-collector", "tempo", "loki", "pyroscope", "prometheus", "langfuse-web", "litellm", "gotrue", "clickhouse"] :
    service => "${service}.${local.namespace}"
  }
  otlp = "http://${local.address.otel-collector}:4318"

  # The ports the services reach each other on: the network's, and the state host's three on
  # Fargate, where they are services too.
  state_ports   = [8123, 9000, 9090, 9091]
  service_ports = setunion([8000, 9999, 4000, 3000, 4317, 4318, 8888, 3200, 3100, 4040], var.state_host == "fargate" ? local.state_ports : [])

  # The application's database: its owner, which migrates, and with grantr the role it works as.
  app_database = replace(var.application.name, "-", "_")
  hosts = {
    app  = "app.${var.domain}"
    auth = "auth.${var.domain}"
  }
  postgres_tls = var.tls_to_data ? "require" : "prefer"
}
