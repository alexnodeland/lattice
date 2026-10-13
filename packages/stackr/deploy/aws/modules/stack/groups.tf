# Who reaches whom (RFC-0004): a security group for each service and one-off task, and a rule for
# each caller, from one table. Every task also has the tasks group, which reaches out over HTTPS;
# the data stores, the state host and the ALB make their own groups, and their rules with the
# services are here.

locals {
  # The services and one-off tasks with a group of their own: the state host's three only where
  # they run on Fargate. auth-keys needs only HTTPS out.
  members = setunion(
    ["app", "gotrue", "litellm", "langfuse-web", "langfuse-worker", "otel-collector", "tempo", "loki", "pyroscope", "grafana", "db-init"],
    local.grantr ? ["db-roles"] : [],
    var.state_host == "fargate" ? ["clickhouse", "prometheus", "prom-label-proxy"] : [],
  )
  # Each task's groups: the tasks group, and its own.
  groups_of = merge(
    { for name in local.members : name => [module.network.security_groups.tasks, aws_security_group.member[name].id] },
    { auth-keys = [module.network.security_groups.tasks] },
  )
  # Each group a rule may name, by its name.
  group = merge(
    { for name in local.members : name => aws_security_group.member[name].id },
    { alb = module.network.security_groups.alb, postgres = module.data.security_group_id, valkey = module.data.security_group_id },
    { for host in module.state_host : "state-host" => host.security_group_id },
  )
  # The group each name in the table is: its own, but on EC2, where the state host runs ClickHouse,
  # Prometheus and prom-label-proxy, theirs is the state host's.
  owner = merge(
    { for name in local.members : name => name },
    { alb = "alb", postgres = "postgres", valkey = "valkey" },
    var.state_host == "ec2" ? { state-host = "state-host", clickhouse = "state-host", prometheus = "state-host", prom-label-proxy = "state-host" } : {},
  )

  # Each service's port, and who calls it there. A name the table doesn't know fails the plan.
  callers = concat(
    [
      { to = "app", port = 8000, from = ["alb"] },
      { to = "gotrue", port = 9999, from = ["alb", "app"] },
      { to = "litellm", port = 4000, from = ["app"] },
      { to = "langfuse-web", port = 3000, from = ["app", "otel-collector", "langfuse-worker"] },
      # OTLP over HTTP, from the application and LiteLLM.
      { to = "otel-collector", port = 4318, from = ["app", "litellm"] },
      # portalr, in the application, reads Tempo and Loki, and Prometheus through prom-label-proxy.
      { to = "tempo", port = 4317, from = ["otel-collector"] },
      { to = "tempo", port = 3200, from = ["grafana", "app"] },
      { to = "loki", port = 3100, from = ["otel-collector", "grafana", "app"] },
      { to = "pyroscope", port = 4040, from = ["grafana"] },
      { to = "postgres", port = 5432, from = concat(
        ["langfuse-web", "langfuse-worker", "litellm", "gotrue", "grafana", "app", "db-init"],
        local.grantr ? ["db-roles"] : [],
      ) },
      { to = "valkey", port = var.valkey.port, from = ["langfuse-web", "langfuse-worker", "litellm"] },
      { to = "clickhouse", port = 8123, from = ["langfuse-web", "langfuse-worker"] },
      { to = "clickhouse", port = 9000, from = ["langfuse-web", "langfuse-worker"] },
      { to = "prometheus", port = 9090, from = ["otel-collector", "tempo", "grafana", "prom-label-proxy"] },
      { to = "prom-label-proxy", port = 9091, from = ["app"] },
    ],
    # On EC2, the state host's Prometheus scrapes the services, as on one machine, and operators
    # reach the admin UIs with SSM port forwarding through it. On Fargate, Prometheus scrapes only
    # itself.
    var.state_host == "ec2" ? [
      { to = "otel-collector", port = 8888, from = ["state-host"] },
      { to = "tempo", port = 3200, from = ["state-host"] },
      { to = "loki", port = 3100, from = ["state-host"] },
      { to = "pyroscope", port = 4040, from = ["state-host"] },
      { to = "grafana", port = 3000, from = ["state-host"] },
      { to = "langfuse-web", port = 3000, from = ["state-host"] },
      { to = "litellm", port = 4000, from = ["state-host"] },
    ] : [],
  )
  # One rule each way for each pair of groups and port. A group's own processes reach each other
  # without one: prom-label-proxy and Prometheus, on the state host.
  rules = { for rule in distinct(flatten([
    for call in local.callers : [
      for from in call.from : { to = local.owner[call.to], port = call.port, from = local.owner[from] }
      if local.owner[from] != local.owner[call.to]
    ]
  ])) : "${rule.to}/${rule.port}/${rule.from}" => rule }
  # The groups something calls.
  called = toset([for rule in values(local.rules) : rule.to])
}

resource "aws_security_group" "member" {
  for_each    = local.members
  name_prefix = "${var.name}-${each.key}-"
  description = contains(local.called, each.key) ? "${each.key}: from its callers" : "${each.key}: nothing calls it"
  vpc_id      = module.network.vpc_id

  # A new description replaces the group: its tasks move to the new one before the old goes.
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "call" {
  for_each                     = local.rules
  security_group_id            = local.group[each.value.to]
  description                  = "${each.value.port} from ${each.value.from}"
  referenced_security_group_id = local.group[each.value.from]
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

resource "aws_vpc_security_group_egress_rule" "call" {
  for_each                     = local.rules
  security_group_id            = local.group[each.value.from]
  description                  = "To ${each.value.to} on ${each.value.port}"
  referenced_security_group_id = local.group[each.value.to]
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

# GoTrue's SMTP server, outside the VPC.
resource "aws_vpc_security_group_egress_rule" "gotrue_smtp" {
  count             = var.auth_smtp == null ? 0 : 1
  security_group_id = aws_security_group.member["gotrue"].id
  description       = "SMTP out, through the NAT gateway"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = var.auth_smtp.port
  to_port           = var.auth_smtp.port
}
