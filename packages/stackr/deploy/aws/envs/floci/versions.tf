# The same stack against Floci, an AWS emulator, for tier 2 (RFC-0004, stackr ADR-0025): local
# state, and the provider pointed at Floci through AWS_ENDPOINT_URL. It fails closed: its keys are
# Floci's own, which AWS refuses, and it applies only to Floci's account, which no AWS account is.
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
}
