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
