# The state host's security group: ClickHouse's, Prometheus's and prom-label-proxy's ports, from the
# services only; out to the services' ports that Prometheus scrapes and operators forward to; and
# out over HTTPS, for lattice's checkout, its images and AWS's APIs, and HTTP, for Ubuntu's arm64
# packages, whose mirror is plain HTTP (signed). The services' rules to and from it are here too.

locals {
  ports = { clickhouse-http = 8123, clickhouse-native = 9000, prometheus = 9090, prom-label-proxy = 9091 }
}

resource "aws_security_group" "this" {
  name        = "${var.name}-state-host"
  description = "The state host: from the services only"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "this" {
  for_each                     = local.ports
  security_group_id            = aws_security_group.this.id
  description                  = "${each.key} from the services"
  referenced_security_group_id = var.services_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "this" {
  for_each          = { http = 80, https = 443 }
  security_group_id = aws_security_group.this.id
  description       = "${upper(each.key)} out, through the NAT gateway: packages, lattice, images and AWS"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = each.value
  to_port           = each.value
}

resource "aws_vpc_security_group_egress_rule" "services" {
  for_each                     = local.ports
  security_group_id            = var.services_security_group_id
  description                  = "To the state host's ${each.key}"
  referenced_security_group_id = aws_security_group.this.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "to_services" {
  for_each                     = { for port in var.service_ports : tostring(port) => port }
  security_group_id            = aws_security_group.this.id
  description                  = "To the services on ${each.key}: scrapes and forwarded admin UIs"
  referenced_security_group_id = var.services_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_ingress_rule" "services_from_state_host" {
  for_each                     = { for port in var.service_ports : tostring(port) => port }
  security_group_id            = var.services_security_group_id
  description                  = "${each.key} from the state host"
  referenced_security_group_id = aws_security_group.this.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}
