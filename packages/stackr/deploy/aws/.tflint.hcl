# TFLint for stackr's AWS recipe (RFC-0004): the recommended rules, and AWS's ruleset, at a pinned
# version, which `tflint --init` fetches and checks against its signature. Renovate's tflint-plugin
# manager moves it.
config {
  call_module_type = "local"
}

plugin "terraform" {
  enabled = true
  preset  = "recommended"
}

plugin "aws" {
  enabled = true
  version = "0.49.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}
