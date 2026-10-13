# The ALB's security group, and the one every task shares (RFC-0004). The ALB takes 443, and 80 to
# redirect, from anywhere. Every task reaches out over HTTPS: to the providers' APIs, AWS's and the
# images' registries. Who reaches whom inside the VPC is the stack module's: each service has a
# group of its own, with the rules from its callers.

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

resource "aws_security_group" "tasks" {
  name        = "${var.name}-tasks"
  description = "Every ECS task: HTTPS out"
  vpc_id      = aws_vpc.this.id
}

resource "aws_vpc_security_group_egress_rule" "tasks_https" {
  security_group_id = aws_security_group.tasks.id
  description       = "HTTPS out, through the NAT gateway: the providers, AWS and the registries"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
