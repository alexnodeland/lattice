# The data stores' security group, which reaches nothing. Who reaches PostgreSQL and Valkey is the
# stack module's: each service that uses one has a rule from its own group.

resource "aws_security_group" "this" {
  name        = "${var.name}-data"
  description = "RDS and ElastiCache: from the services that use them"
  vpc_id      = var.vpc_id
}
