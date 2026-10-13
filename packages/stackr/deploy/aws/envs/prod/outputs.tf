output "hosts" {
  description = "The names users reach."
  value       = module.stack.hosts
}

output "state_host_instance_id" {
  description = "The state host, for SSM port forwarding to the admin UIs."
  value       = module.stack.state_host_instance_id
}

output "secrets_written_elsewhere" {
  description = "The secrets an operator writes after the first apply."
  value       = module.stack.secrets_written_elsewhere
}

output "one_off_task_definitions" {
  description = "The one-off tasks, to run again by hand."
  value       = module.stack.one_off_task_definitions
}

output "cluster_arn" {
  description = "The ECS cluster: aws ecs update-service and run-task name it."
  value       = module.stack.cluster_arn
}

output "run_task_network" {
  description = "The subnets the one-off tasks run in, and each one's security groups, to run one again by hand."
  value       = module.stack.run_task_network
}

output "alb_dns_name" {
  description = "The ALB's own name, which app.<domain> and auth.<domain> alias."
  value       = module.stack.alb_dns_name
}
