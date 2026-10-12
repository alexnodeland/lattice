# ADR-0029: The AWS modules, and tier 1

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the first part of phase 3 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the tools, tier 1's checks, and the `network`, `secrets` and `data` modules. `edge`, `ecs-service`, `state-host`, `stack` and the two roots follow, then the thin images. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 pins OpenTofu and TFLint in `.prototools`, through community plugins pinned to a commit, and checks every change to `deploy/aws/**` with tier 1: formatting, validation, TFLint, checkov over the modules and the plan's JSON, and `tofu test` against a mocked AWS. Building it found that proto loads a plugin only from a configuration it has been told to trust, whoever wrote the plugin; that OpenTofu's tests can't share mocks between files, nor mock an ephemeral resource; and that checkov's scan of the HCL can't follow resources made `for_each` beside the one it checks.

## Decision

### The tools

- **OpenTofu 1.13 and TFLint, from plugins of lattice's own:** two short TOML files in `deploy/aws/tools/`, which download each tool from its own GitHub releases and check it against their checksums. `.prototools` names them with `file://` locators, so nothing outside lattice decides what runs. proto loads them once the file is trusted: `proto trust .prototools`, which the dev container and the CI job run.
- **Renovate moves them:** a custom manager reads the two versions in `.prototools` against each tool's GitHub releases. TFLint's AWS ruleset is pinned in `deploy/aws/.tflint.hcl`, which Renovate's TFLint manager moves, and checkov's version in `deploy/aws/check`, which a second custom manager reads against PyPI.
- **checkov runs through `uvx`** at that exact version, so its dependencies stay out of the workspace's one resolution.

### Tier 1

- **`deploy/aws/check`**, stackr's `aws` task: `tofu fmt`, `tofu validate` of each module, TFLint with AWS's ruleset, checkov with `deploy/aws/.checkov.yaml`, and `tofu test`. Each check checkov skips is in that file with its reason.
- **Its own CI job, `AWS (tier 1)`,** with the tools and a cache of the providers, through `scripts/affected.py`: it runs on every pull request that affects stackr, which is more often than the RFC's "touches `deploy/aws/**`", and costs a minute.
- **The tests plan each module against a mocked AWS,** from `deploy/aws`, whose `versions.tf` is a root that deploys nothing: a file per module in `tests/`, each `run` naming its module. Each file mocks what the provider checks even when mocked: a policy document's JSON, and an ARN where another resource takes one. They assert shapes: which resources a module plans, what its variables refuse, and that a generated secret has no value in state. Behaviour is tier 2's.

### The modules

- **`network`:** a VPC across two zones, with a public and a private subnet in each, one NAT gateway, flow logs, a default security group that lets nothing through, and a group each for the ALB, the services and the data stores. The services' and the data stores' groups take traffic only from other groups.
- **`secrets`:** each generated secret is a password made for it alone, ephemeral, written to Secrets Manager through `secret_string_wo` once and again only when its version is raised: the password itself, or a JSON object of templates, such as a database URL with the password in it, which ECS injects key by key. Others are made empty, for a one-off task or an operator to write. Deleting one is recoverable for a window that is a variable.
- **`data`:** RDS for PostgreSQL 17, its master `postgres` with the password RDS manages, TLS required (`rds.force_ssl`), encrypted, and kept on destroy unless its variables say otherwise; ElastiCache for Valkey with `noeviction`, encryption in transit and at rest, and its auth token through a write-only argument; and the buckets (Langfuse's, the telemetry stores', and backups), private, encrypted, versioned, with TLS required.
- **Valkey's auth token reaches `data` as an ephemeral variable,** which the caller reads from its secret. That keeps the module testable: OpenTofu can't mock an ephemeral resource.

### Where this departs from RFC-0004

- **Plugins of lattice's own, not community ones pinned to a commit.** Trust is needed either way, and a plugin is a dozen lines.
- **checkov reads the modules' HCL, not yet the plan's JSON.** A plan needs a root, and the roots come with the rest of the modules; the checks the HCL scan can't follow are skipped with that reason, and the tests check them.
- **Tier 1 runs whenever stackr is affected,** not only when `deploy/aws/**` changes.

## Consequences

- Easier: every change to the AWS modules is formatted, linted, scanned and tested in CI, with no AWS and no Floci.
- Harder: anyone who works on the modules runs `proto trust .prototools` once.
- Harder: each test file repeats the few mocks it needs.
- Next: the plan's JSON in checkov, once `envs/floci` exists.
