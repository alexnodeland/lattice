# The ALB's and the services' security groups (RFC-0004). The ALB takes 443, and 80 to redirect,
# from anywhere, and reaches only the services' ports it forwards to. The services take traffic
# only from the ALB and from each other, each on the ports they listen on, and reach out only over
# HTTPS: to the providers' APIs, AWS's and the images' registries. The data stores and the state
# host make their own groups, with the rules between them and the services.

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
  for_each                     = { for port in var.alb_target_ports : tostring(port) => port }
  security_group_id            = aws_security_group.alb.id
  description                  = "To the services on ${each.key}"
  referenced_security_group_id = aws_security_group.services.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_security_group" "services" {
  name        = "${var.name}-services"
  description = "The ECS services: from the ALB, and from each other, on their ports"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_ingress_rule" "from_alb" {
  for_each                     = { for port in var.alb_target_ports : tostring(port) => port }
  security_group_id            = aws_security_group.services.id
  description                  = "${each.key} from the ALB"
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_ingress_rule" "between_services" {
  for_each                     = { for port in var.service_ports : tostring(port) => port }
  security_group_id            = aws_security_group.services.id
  description                  = "${each.key} from the services"
  referenced_security_group_id = aws_security_group.services.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "between_services" {
  for_each                     = { for port in var.service_ports : tostring(port) => port }
  security_group_id            = aws_security_group.services.id
  description                  = "To the services on ${each.key}"
  referenced_security_group_id = aws_security_group.services.id
  ip_protocol                  = "tcp"
  from_port                    = each.value
  to_port                      = each.value
}

resource "aws_vpc_security_group_egress_rule" "services_https" {
  security_group_id = aws_security_group.services.id
  description       = "HTTPS out, through the NAT gateway: the providers, AWS and the registries"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
