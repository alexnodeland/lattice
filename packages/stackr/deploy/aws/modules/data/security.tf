# The data stores' security group: PostgreSQL's and Valkey's ports, from the services only, and
# nothing out. The services' egress to them is here too, with the ports.

locals {
  ports = { postgresql = 5432, valkey = var.valkey.port }
}

resource "aws_security_group" "this" {
  name        = "${var.name}-data"
  description = "RDS and ElastiCache: from the services only"
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

resource "aws_vpc_security_group_egress_rule" "services" {
  for_each                     = local.ports
  security_group_id            = var.services_security_group_id
  description                  = "To ${each.key}"
  referenced_security_group_id = aws_security_group.this.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}
