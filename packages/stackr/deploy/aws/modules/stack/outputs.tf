output "hosts" {
  description = "The names users reach: app.<domain> and auth.<domain>."
  value       = module.edge.hosts
}

output "alb_dns_name" {
  description = "The ALB's own name, which the hosts alias."
  value       = module.edge.alb_dns_name
}

output "cluster_arn" {
  description = "The ECS cluster, which run-task names."
  value       = aws_ecs_cluster.this.arn
}

output "one_off_task_definitions" {
  description = "The one-off tasks' definitions, by name, for an operator to run again by hand."
  value = merge(
    { db-init = module.db_init.task_definition_arn, auth-keys = module.auth_keys.task_definition_arn },
    { for task in module.db_roles : "db-roles" => task.task_definition_arn },
  )
}

output "run_task_network" {
  description = "The subnets and security group a one-off task runs in."
  value = {
    subnet_ids        = module.network.private_subnet_ids
    security_group_id = module.network.security_groups.services
  }
}

output "state_host_instance_id" {
  description = "The state host, which SSM port forwarding names as its target; none on Fargate."
  value       = one(module.state_host[*].instance_id)
}

output "secrets_written_elsewhere" {
  description = "The secrets an operator writes, by key: the providers' API keys and GoTrue's SMTP password."
  value       = { for key, arn in module.secrets.arns : key => arn if startswith(key, "litellm-") && endswith(key, "-api-key") || key == "auth-smtp-password" }
}
