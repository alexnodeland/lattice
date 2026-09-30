# ADR-0004: One GitHub App for release-please and Renovate

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

Two tools open pull requests in lattice: release-please, its release pull request ([ADR-0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)), and Renovate, its dependency updates ([ADR-0005](0005-renovate-runs-in-lattices-own-actions.md)). A pull request opened, or a commit pushed, with a workflow's own `GITHUB_TOKEN` starts no workflow runs. CI and Title would never report on those pull requests, and the ruleset requires both ([ADR-0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md)), so none of them could merge.

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) was silent on release-please's token, and assumed Renovate would run as Mend's hosted app, with an identity of its own. On the day, Renovate moved into lattice's own Actions, so both needed an identity that isn't the workflow's.

## Decision

- **One GitHub App, `alexnodeland-lattice`,** installed on lattice alone, acts for both. Its pull requests and commits come from `alexnodeland-lattice[bot]`.
- **Each workflow mints a token for each run** with `actions/create-github-app-token`, from the `LATTICE_APP_CLIENT_ID` and `LATTICE_APP_PRIVATE_KEY` secrets, and **narrows it to what that workflow needs**, in the action's `permission-*` inputs.

| Workflow | The token's permissions |
|---|---|
| `release.yml` | Contents and pull requests: write |
| `renovate.yml` | Contents, pull requests, issues, checks, commit statuses and workflows: write. Administration and Dependabot alerts: read |

- **The App holds the union,** and nothing more: those permissions, and metadata, which is always read.
- **Only the step that needs the App uses its token.** `release.yml`'s build jobs attach the wheels to the releases with the workflow's own token.

## Options considered

| Option | Their pull requests run CI and Title | What the credential reaches | Secrets |
|---|---|---|---|
| **One App, a token narrowed for each run (chosen)** | Yes | lattice, and in each run only what its workflow needs | One pair |
| An App for each tool | Yes | lattice, each App only what its tool needs | Two pairs, and two Apps to keep |
| A personal access token | Yes | Every repository the maintainer can write to, until it expires | One, which expires |
| The workflow's `GITHUB_TOKEN` | No: its pull requests could never merge | lattice | None |

## Trade-off analysis

A second App would keep each tool's permissions apart at the App, where one App keeps them apart per run, with each workflow's `permission-*` inputs. The per-run narrowing gives the same result at the token, with one identity, one key to rotate and one installation to review. A personal token would be simpler still, and would lend both tools the maintainer's reach across every repository.

## Consequences

- Easier: release pull requests and dependency updates pass through the same ruleset and checks as anyone's.
- Harder: the App holds both tools' permissions, and what keeps a run to its own is its workflow's `permission-*` inputs. A change to them deserves the scrutiny of a change to the App.
- Harder: the App's private key is a secret to rotate.
