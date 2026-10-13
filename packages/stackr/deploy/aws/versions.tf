# The root `tofu test` runs the modules' tests from (tests/), against a mocked AWS. It deploys
# nothing: envs/prod and envs/floci are the roots that do.
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
