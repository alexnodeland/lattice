# ADR-0011: CodeQL on every change, and Scorecard every week

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) puts CodeQL (Python, TypeScript) and OpenSSF Scorecard, weekly, under supply chain, in their own workflows, `codeql.yml` and `scorecard.yml`, in phase 6. It doesn't say when CodeQL runs, or what happens to what either finds.

GitHub offers CodeQL two ways. Its default setup is a repository setting, with no workflow, and it can't run beside a workflow of lattice's own. An advanced setup is a workflow, hardened and linted as every other one is ([architecture](../architecture.md#ci)). portalr's TypeScript is in `packages/portalr/web/`. zizmor and actionlint already check the workflows, in the hooks and in CI.

Scorecard publishes its result to the OpenSSF only from the default branch, and only when its job uses the actions it allows, with no top-level `env` or `defaults`.

## Decision

- **`codeql.yml` analyses the Python and the TypeScript** (`python`, `javascript-typescript`) on every pull request, on every push to `main`, and every Monday, so new queries reach code that hasn't changed. Neither needs a build (`build-mode: none`). A pull request's newer push cancels its older analysis; `main`'s analyses all finish. CodeQL's `actions` language stays off, since zizmor covers the workflows.
- **`scorecard.yml` runs every Monday, and by hand,** on `main`. It publishes the result to the OpenSSF's API (`publish_results`), and uploads its findings to code scanning.
- **Both are advanced setups,** in lattice's own workflows: pinned by commit with the version beside it, `permissions: {}` at the top, `contents: read` and `security-events: write` per job (and `id-token: write` for Scorecard's signed result), and no credentials kept by the checkout. GitHub's default CodeQL setup stays off.
- **Neither is part of `CI`.** CodeQL's alerts show on the pull request, through GitHub's code scanning check. An alert is fixed, or dismissed with its reason, as `osv-scanner.toml` records an advisory that doesn't apply ([ADR-0008](0008-one-resolution-litellm-held-at-1-83-0.md)). Scorecard's findings are read each week, and a finding worth acting on becomes an issue.

## Options considered

### CodeQL

| Option | Runs | Configuration |
|---|---|---|
| **An advanced setup, `codeql.yml` (chosen)** | Pull requests, `main`, weekly | In the repository, reviewed and linted like every workflow |
| GitHub's default setup | Pull requests, `main`, weekly | A repository setting; actions that zizmor and Renovate never see |

### When Scorecard runs

| Option | What it costs |
|---|---|
| **Weekly, and by hand (chosen)** | One short job a week |
| On every push to `main` too | A score for every merge, when what it scores changes rarely |

## Trade-off analysis

The default setup is less to keep, but it hides the analysis in a setting and can't be pinned, linted or changed in review, which every other check in lattice is. Scorecard measures practices that move with settings and workflows, not with each commit, so a weekly score says as much as one per merge.

## Consequences

- Easier: an injection, a path traversal or an unsafe deserialisation that CodeQL knows shows on the pull request that adds it.
- Easier: Scorecard's public score says how lattice is run, and its findings name what would raise it.
- Harder: Scorecard runs only on `main`, so this workflow is first run after it merges, by hand.

## Amendment (2026-10-24)

On a pull request, CodeQL runs only when a Python, TypeScript or JavaScript file changes (`paths` on `pull_request`), not for documentation or workflow changes alone: 157 runs a day competed with `CI` for 20 runners. It is not a required check, so a pull request that doesn't trigger it leaves nothing pending. Pushes to `main` and the weekly run are unchanged.
