# envs/prod, planned against a mocked AWS with prod.tfvars.example (tier 1): the example is a
# deployment the root accepts. deploy/aws/check runs it with -var-file=prod.tfvars.example.

mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_partition" {
    defaults = { partition = "aws" }
  }
  mock_data "aws_region" {
    defaults = { region = "us-east-1" }
  }
  mock_data "aws_subnet" {
    defaults = { availability_zone = "us-east-1a" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf" }
  }
  mock_resource "aws_secretsmanager_secret_version" {
    defaults = { secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/mocked-AbCdEf" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address            = "stackr.mocked.us-east-1.rds.amazonaws.com"
      port               = 5432
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-1:000000000000:secret:rds!db-mocked-AbCdEf", kms_key_id = "", secret_status = "active" }]
    }
  }
  mock_resource "aws_elasticache_replication_group" {
    defaults = { primary_endpoint_address = "master.stackr.mocked.cache.amazonaws.com" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { id = "stackr-mocked", arn = "arn:aws:s3:::stackr-mocked" }
  }
  mock_resource "aws_acm_certificate" {
    defaults = {
      arn = "arn:aws:acm:us-east-1:000000000000:certificate/mocked"
      domain_validation_options = [
        { domain_name = "app.example.com", resource_record_name = "_a.app.example.com.", resource_record_type = "CNAME", resource_record_value = "_a.acm-validations.aws." },
        { domain_name = "auth.example.com", resource_record_name = "_a.auth.example.com.", resource_record_type = "CNAME", resource_record_value = "_b.acm-validations.aws." },
      ]
    }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:loadbalancer/app/stackr/mocked" }
  }
  mock_resource "aws_lb_listener" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:listener/app/stackr/mocked/mocked" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-1:000000000000:targetgroup/stackr/mocked" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mocked" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-1:000000000000:log-group:/stackr/mocked" }
  }
  mock_resource "aws_ebs_volume" {
    defaults = { id = "vol-0123456789abcdef0" }
  }
  mock_resource "aws_service_discovery_service" {
    defaults = { arn = "arn:aws:servicediscovery:us-east-1:000000000000:service/srv-mocked" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { arn = "arn:aws:ecs:us-east-1:000000000000:cluster/stackr" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-1:000000000000:task-definition/stackr-mocked:1" }
  }
}

run "prod_plans_the_example_deployment" {
  command = plan

  assert {
    condition     = output.hosts == { app = "app.example.com", auth = "auth.example.com" }
    error_message = "The example deployment serves app.<domain> and auth.<domain>."
  }
  assert {
    condition     = toset(keys(output.one_off_task_definitions)) == toset(["db-init", "auth-keys", "db-roles"])
    error_message = "The example's application, with grantr by default, has db-init, auth-keys and db-roles."
  }
}
