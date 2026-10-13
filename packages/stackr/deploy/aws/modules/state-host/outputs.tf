output "address" {
  description = "The state host's fixed private address."
  value       = var.private_ip
}

output "instance_id" {
  description = "The instance, which SSM port forwarding names as its target."
  value       = aws_instance.this.id
}
