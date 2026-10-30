# AGENTS.md

The root [AGENTS.md](../AGENTS.md) applies; this adds what is specific to workflows and actions. Each workflow's header comment says what it runs and why; read it first.

## Workflows

| File | What it does |
|---|---|
| `workflows/ci.yml` | Pull requests: each job runs its task over affected projects (`scripts/affected.py`); `CI` is required |
| `workflows/title.yml` | Conventional Commit title and the public-API break check; `Title` is required |
| `workflows/nightly.yml` | Every project's checks, deep specs, images, osv-scanner, lychee links |
| `workflows/docs.yml` | Builds and publishes the site to GitHub Pages from main |
| `workflows/release.yml` | release-please, wheel builds, attestations, PyPI |
| `workflows/renovate.yml` | Renovate, as lattice's GitHub App |
| `workflows/codeql.yml`, `workflows/scorecard.yml` | Code scanning and OpenSSF Scorecard |
| `actions/toolchain/` | Installs proto and `.prototools`' tools, from cache with retries (ADR-0017) |
| `actions/disk/` | Frees the runner's disk (unused toolchains, preinstalled images) and prints `df -h`, for the jobs that start stacks |

## Rules

- Pin every third-party action to a full commit SHA with its version in a comment (`uses: owner/action@<sha> # v1.2.3`). Renovate updates them.
- Install tools with `./.github/actions/toolchain`, not setup-* actions.
- Give every job a `timeout-minutes` (ADR-0007) and the narrowest `permissions`.
- Run `moon run lattice:workflows` (actionlint and zizmor) after any change here. A zizmor finding is fixed, or ignored on its line with a reason, as the existing ones are.
- Don't add a required check without saying so in the PR; the ruleset requires only `CI` and `Title`.
- [PULL_REQUEST_TEMPLATE.md](PULL_REQUEST_TEMPLATE.md) is the PR body: keep its checklist.
