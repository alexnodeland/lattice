# The modules' templates, rendered with sample values for deploy/aws/check: the state host's user
# data, which shellcheck reads, and GoTrue's proxy's Caddyfile, which tests/auth-proxy runs. Needs
# no provider, and creates nothing.
terraform {
  required_version = ">= 1.13"
}

variable "trusted_proxies" {
  description = "The ranges the proxy trusts, in place of the ALB's subnets."
  type        = string
}

output "user_data" {
  description = "The state host's user data."
  value = templatefile("${path.module}/../../../modules/state-host/user-data.sh.tftpl", {
    volume_id      = "vol-0123456789abcdef0"
    address        = "10.40.128.10"
    lattice_commit = "0123456789abcdef0123456789abcdef01234567"
    secret_arn     = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-password-AbCdEf"
    admin_arn      = "arn:aws:secretsmanager:us-east-1:000000000000:secret:stackr/clickhouse-admin-password-AbCdEf"
    region         = "us-east-1"
    aws_cli_image  = "amazon/aws-cli"
  })
}

output "caddyfile" {
  description = "GoTrue's proxy's Caddyfile."
  value = templatefile("${path.module}/../../../modules/edge/auth-proxy.Caddyfile.tftpl", {
    port            = 9999
    gotrue_port     = 9998
    trusted_proxies = var.trusted_proxies
  })
}
