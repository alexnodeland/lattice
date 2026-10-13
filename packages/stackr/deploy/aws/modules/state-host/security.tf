# The state host's security group: ClickHouse's, Prometheus's and prom-label-proxy's ports, from the
# services only; and out over HTTP and HTTPS alone, for its packages, lattice's checkout, its images
# and Secrets Manager. The services' egress to it is here too, with the ports.

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
