# The state host's security group: out over HTTPS, for lattice's checkout, its images and AWS's
# APIs, and HTTP, for Ubuntu's arm64 packages, whose mirror is plain HTTP (signed). Who reaches
# ClickHouse, Prometheus and prom-label-proxy, and whom Prometheus scrapes and operators forward to,
# is the stack module's.

resource "aws_security_group" "this" {
  name        = "${var.name}-state-host"
  description = "The state host: from the services that use it"
  vpc_id      = var.vpc_id
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
