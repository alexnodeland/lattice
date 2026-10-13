output "task_definition_arn" {
  description = "The task definition, which run-task names for a one-off."
  value       = aws_ecs_task_definition.this.arn
}

output "task_role_name" {
  description = "The task role, to which a caller may attach more."
  value       = aws_iam_role.task.name
}

output "address" {
  description = "The service's private name, and its port; none for a one-off task."
  value       = var.one_off ? null : { name = aws_service_discovery_service.this[0].name, port = var.container.port }
}
