# AGENTS.md: deploy/aws

The root and [stackr](../../AGENTS.md) AGENTS.md files apply; this adds the AWS recipe's rules.

- This is OpenTofu, not Terraform: use `tofu` from lattice's `.prototools`, never `terraform`.
- Roots are `envs/prod` and `envs/floci`; reusable code is in `modules/<name>/`; their tests are `tests/<module>.tofutest.hcl`.
- Run `moon run stackr:aws` (`deploy/aws/check`) after any change: `tofu fmt`, validate against the committed lock files, TFLint with the AWS ruleset, checkov, the modules' tests against a mocked AWS, and the rendered templates through shellcheck.
- Don't add inline checkov or TFLint skips. A checkov skip goes in that module's `.checkov.yaml` with its reason.
- Keep lock files committed and consistent with the providers the tests use.
- `moon run stackr:aws-tier2` runs the recipe against Floci on an arm64 Docker; run it when you change a module or an image the stack runs.
- GoTrue's image in `modules/stack/locals.tf` must match `versions.env`'s Supabase CLI (`moon run stackr:gotrue`).
- Never run `tofu apply` against real AWS.
