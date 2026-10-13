output "vpc_id" {
  description = "The VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "The public subnets, one per zone: the ALB's and the NAT gateway's."
  value       = [for zone in var.zones : aws_subnet.public[zone].id]
}

output "private_subnet_ids" {
  description = "The private subnets, one per zone: everything else."
  value       = [for zone in var.zones : aws_subnet.private[zone].id]
}

output "security_groups" {
  description = "The ALB's and the services' security groups."
  value = {
    alb      = aws_security_group.alb.id
    services = aws_security_group.services.id
  }
}

output "vpc_cidr" {
  description = "The VPC's address range."
  value       = aws_vpc.this.cidr_block
}
