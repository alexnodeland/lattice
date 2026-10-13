# ADR-0029: The AWS modules, and tier 1

**Status:** Accepted, amended by [ADR-0034](0034-the-stack-on-aws.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds the first part of phase 3 of [RFC-0004](../rfcs/0004-hosting-recipes.md): the tools, tier 1's checks, and the `network`, `secrets` and `data` modules. `edge`, `ecs-service`, `state-host`, `stack` and the two roots follow, then the thin images. Records what the RFC left to the build, and where it departs from it.

## Context

RFC-0004 pins OpenTofu and TFLint in `.prototools`, through community plugins pinned to a commit, and checks every change to `deploy/aws/**` with tier 1: formatting, validation, TFLint, checkov over the modules and the plan's JSON, and `tofu test` against a mocked AWS. Building it found that:

- proto loads a plugin only from a configuration it has been told to trust, whoever wrote the plugin;
- OpenTofu's tests can't share mocks between files. In OpenTofu 1.13.1, a test's `mock_resource` doesn't answer for the ephemeral resource of the same type, and there is no block of its own for one;
- checkov's scan of the HCL can't follow resources made `for_each` beside the one it checks.

## Decision

### The tools

- **OpenTofu 1.13 and TFLint come from plugins of lattice's own:** two short TOML files in `deploy/aws/tools/`. Each downloads its tool from the tool's own GitHub releases and checks it against the release's checksums. `.prototools` names them with `file://` locators, so nothing outside lattice decides what runs.
- **proto loads them only from a trusted file.** In CI, `setup-toolchain` installs the other tools and passes over these two, with a warning; the tier 1 job then runs `proto trust .prototools` and installs them. The dev container trusts the file in its setup. Anyone else runs `proto trust .prototools` once.
- **Their signatures aren't checked.** Both tools sign their checksums with cosign; proto checks the checksums, not the signatures, and so does tier 1. That gap is recorded here.
- **The providers are locked.** `deploy/aws/.terraform.lock.hcl` is committed, made with `tofu providers lock` for `linux_amd64`, `darwin_arm64` and `darwin_amd64`. `check` initializes with `-lockfile=readonly`, and CI caches the providers by that file and the runner's system.
- **Renovate moves them:**
  - its custom manager reads OpenTofu's and TFLint's versions in `.prototools` against each tool's GitHub releases (a version starts with a digit, which the plugins' locators don't);
  - its TFLint manager moves the AWS ruleset pinned in `deploy/aws/.tflint.hcl`;
  - its Terraform manager moves the providers.
- **checkov runs through `uvx`,** at an exact version, with its dependencies as they were on a date (`--exclude-newer`), outside the workspace's resolution. The version and the date move together, by hand.

### Tier 1

- **`deploy/aws/check`** is stackr's `aws` task. It runs:
  - `tofu fmt`;
  - the locked providers;
  - TFLint with AWS's ruleset, which it fetches with `GITHUB_TOKEN`;
  - checkov over each module;
  - `tofu test`, which validates each module as it plans it.
- **Each module has a `.checkov.yaml`.** Every check skipped there is skipped for that module alone, with its reason, so another module that opens SSH or port 80 to the world still fails.
- **Its own CI job, `AWS (tier 1)`,** runs through `scripts/affected.py`.
- **The tests plan or apply each module against a mocked AWS,** from `deploy/aws`, whose `versions.tf` is a root that deploys nothing. There is a file per module in `tests/`, and each `run` names its module. Each file mocks what the provider checks even when mocked: an ARN where another resource takes one, a caller's account, and RDS's managed secret.
- **The tests assert the security properties:**
  - no subnet hands out public addresses, and the default group lets nothing through;
  - only the ALB takes an address range, on 80 and 443 alone;
  - the services take traffic only from groups, port by port, never 22 or 3389;
  - the flow logs' role trusts only this account;
  - no generated secret has a value in state;
  - RDS is encrypted, private, TLS-only and backed up;
  - Valkey is encrypted, on its port, behind a token;
  - the buckets are private, versioned, tidied and TLS-only;
  - each variable refuses what AWS would.
- **Behaviour is tier 2's.**

### The modules

- **`network`:**
  - a VPC across two zones, each with a public and a private subnet, neither handing out public addresses;
  - one NAT gateway;
  - flow logs, whose role trusts only this account's flow logs (`aws:SourceAccount`, `aws:SourceArn`), against the confused deputy;
  - a default security group that lets nothing through;
  - the ALB's group: 80 and 443 from anywhere, and out only to the ports it forwards to;
  - the services' group: in from the ALB on those ports, and from each other on the ports they listen on, and out only to each other and to 443.
- **`secrets`:**
  - each generated secret is a password made for it alone, ephemeral, written to Secrets Manager through `secret_string_wo` once, and again only when its version is raised;
  - the secret is the password itself, or a JSON object of templates, such as a database URL with the password in it, which ECS injects key by key;
  - a changed template needs a raised version, and so rotates the secret;
  - others are made empty, for a one-off task or an operator to write;
  - deleting one is recoverable for a window of 0, or 7 to 30 days.
- **`data`:**
  - RDS for PostgreSQL 17: its master is `postgres`, with the password RDS manages; TLS is required (`rds.force_ssl`); it is encrypted, keeps 1 to 35 days of backups, and is kept on destroy unless its variables say otherwise, with a final snapshot named uniquely;
  - ElastiCache for Valkey: `noeviction`, encryption in transit and at rest, and its auth token through a write-only argument, whose version moves with the token's secret;
  - the buckets (Langfuse's, the telemetry stores', and backups), each named `<name>-<role>-` and a unique suffix, since bucket names are global: private, encrypted, versioned, tidied, with TLS required;
  - its own security group, which takes PostgreSQL's and Valkey's ports from the services only and reaches nothing, and the services' egress to it.
- **Valkey's auth token reaches `data` as an ephemeral variable,** which the caller reads from its secret. That keeps the module testable.

### Where this departs from RFC-0004

- **Plugins of lattice's own, not community ones pinned to a commit.** Trust is needed either way, and a plugin is a dozen lines.
- **checkov reads the modules' HCL, not yet the plan's JSON.** A plan needs a root, and the roots come with the rest of the modules. The checks the HCL scan can't follow are skipped, in that module only, with that reason, and the tests check them.
- **Tier 1 runs whenever stackr is affected,** not only when `deploy/aws/**` changes. With mocks, it costs a minute.

## Consequences

- Easier: every change to the AWS modules is formatted, linted, scanned and tested in CI, against locked providers, with no AWS and no Floci.
- Harder: anyone who works on the modules runs `proto trust .prototools` once, and checkov's version moves by hand.
- Harder: each test file repeats the few mocks it needs.
- Next: the plan's JSON in checkov, once `envs/floci` exists. Also next: the tools' cosign signatures, if proto learns to check them.
