# One security group for each kind of traffic. Each lets in only what calls it; every group may
# reach out, through the NAT gateway, since the services call the providers' APIs.

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "The ALB: HTTPS, and HTTP to redirect, from anywhere"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.alb.id
  description       = "Port ${each.key} from anywhere"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.key)
  to_port           = tonumber(each.key)
}

resource "aws_vpc_security_group_egress_rule" "alb" {
  security_group_id            = aws_security_group.alb.id
  description                  = "To the services"
  referenced_security_group_id = aws_security_group.services.id
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
}

resource "aws_security_group" "services" {
  name        = "${var.name}-services"
  description = "The ECS services: from the ALB, and from each other"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "services" {
  for_each = {
    alb      = aws_security_group.alb.id
    services = aws_security_group.services.id
  }
  security_group_id            = aws_security_group.services.id
  description                  = "From ${each.key}"
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 0
  to_port                      = 65535
}

# The data stores: PostgreSQL, Valkey, and the state host's ClickHouse, Prometheus and
# prom-label-proxy, from the services only.
resource "aws_security_group" "data" {
  name        = "${var.name}-data"
  description = "RDS, ElastiCache and the state host: from the services only"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "data" {
  for_each = {
    postgresql        = 5432
    valkey            = 6379
    clickhouse-http   = 8123
    clickhouse-native = 9000
    prometheus        = 9090
    prom-label-proxy  = 9091
  }
  security_group_id            = aws_security_group.data.id
  description                  = "${each.key} from the services"
  referenced_security_group_id = aws_security_group.services.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "out" {
  for_each          = { services = aws_security_group.services.id, data = aws_security_group.data.id }
  security_group_id = each.value
  description       = "Out, through the NAT gateway"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
