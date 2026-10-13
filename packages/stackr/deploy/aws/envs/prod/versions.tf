# The root an operator applies (RFC-0004). Its state is in S3, with S3's own lock file: one bucket
# per account, made once by hand (README.md), and one key per deployment, given at init. CI never
# applies it.
terraform {
  required_version = ">= 1.13"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.8"
    }
  }

  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}
