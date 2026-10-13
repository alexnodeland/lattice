output "vpc_id" {
  description = "The VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "The public subnets, one per zone: the ALB's and the NAT gateway's."
  value       = [for zone in var.zones : aws_subnet.public[zone].id]
}

output "public_subnet_cidrs" {
  description = "The public subnets' ranges: the ALB's nodes' addresses, which GoTrue's proxy trusts."
  value       = [for zone in var.zones : local.public[zone]]
}

output "private_subnet_ids" {
  description = "The private subnets, one per zone: everything else."
  value       = [for zone in var.zones : aws_subnet.private[zone].id]
}

output "private_subnet_cidrs" {
  description = "The private subnets' ranges, known at plan: the state host's fixed address is in the first."
  value       = [for zone in var.zones : local.private[zone]]
}

output "security_groups" {
  description = "The ALB's security group, and the tasks group, which every task has."
  value = {
    alb   = aws_security_group.alb.id
    tasks = aws_security_group.tasks.id
  }
}

output "vpc_cidr" {
  description = "The VPC's address range."
  value       = aws_vpc.this.cidr_block
}
