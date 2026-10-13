output "task_definition_arn" {
  description = "The task definition, which run-task names for a one-off, once its roles may do what it needs."
  value       = aws_ecs_task_definition.this.arn
  depends_on  = [aws_iam_role_policy.execution, aws_iam_role_policy.secrets, aws_iam_role_policy.task]
}

output "service_arn" {
  description = "The ECS service, which others may wait for; none for a one-off task."
  value       = one(aws_ecs_service.this[*].id)
}

output "after" {
  description = "What the service waits for, and is deployed again after."
  value       = var.after
}

output "task_role_policy" {
  description = "What its tasks may do in AWS, as given."
  value       = var.task_role_policy_json
}

output "target_group_arn" {
  description = "The ALB target group its tasks register with, if any."
  value       = var.target_group_arn
}

output "task_role_name" {
  description = "The task role, to which a caller may attach more."
  value       = aws_iam_role.task.name
}

output "address" {
  description = "The service's private name, and its port; none for a one-off task."
  value       = var.one_off ? null : { name = aws_service_discovery_service.this[0].name, port = var.container.port }
}

output "containers" {
  description = "Its containers, as its task definition gives them to ECS: settings, and secrets by reference only."
  value       = jsondecode(aws_ecs_task_definition.this.container_definitions)
}

output "security_group_ids" {
  description = "Its tasks' security groups."
  value       = var.security_group_ids
}
