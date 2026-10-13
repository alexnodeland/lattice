# The same stack against Floci, an AWS emulator, for tier 2 (RFC-0004, stackr ADR-0025): local
# state, the provider pointed at Floci through AWS_ENDPOINT_URL, and Floci's catalog of sizes. It
# never reaches AWS.
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
