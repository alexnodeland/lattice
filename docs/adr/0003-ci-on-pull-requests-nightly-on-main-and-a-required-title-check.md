# ADR-0003: CI on pull requests, Nightly on main, and a required Title check

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) planned one required check, `CI`: the last job of `ci.yml`, which `re-actors/alls-green` passes only when every other job does. `ci.yml` would run on pull requests and on `main`, and the pull request title's lint would be one of its jobs, on pull requests only. alls-green counts a skipped job as a failure, so the jobs that run only on pull requests would be listed in its `allowed-skips`.

The setup found two problems with that:

- **A title is edited after CI has run.** The title becomes the squash commit on `main`, and release-please reads it to decide what to release ([ADR-0006](0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)). A workflow reruns on an edited title only if it listens for `edited`, and `ci.yml` doesn't. So a title lint inside CI keeps the result it had when the pull request was opened or last pushed: a title broken afterwards merges, and one fixed afterwards stays red until the next push.
- **`main` would be checked twice.** `nightly.yml` already runs every project's `check` on each push to `main`, which `ci.yml`'s affected projects on `main` would repeat.

## Decision

- **`ci.yml` runs on pull requests only.** Every job runs on every pull request, even if only to find nothing affected, so CI's alls-green needs no `allowed-skips`.
- **Title is a workflow of its own,** `title.yml`, on `opened`, `edited`, `synchronize` and `reopened`. It checks the title against the Conventional Commits types lattice uses. Scopes stay as they are, the packages' module and area names, and aren't listed: the history has 33, and a new module brings a new one.
- **`CI` and `Title` are both required**, from GitHub Actions, on branches that are up to date with `main`, in the ruleset that `main` shares with the siblings' repositories: no deletion, no force push, linear history, and squash-only pull requests. GitHub offers merge queues only to organizations, and `alexnodeland` is a personal account, so there is none.
- **`nightly.yml` checks `main`,** on every push and every night: every project's `check`, the reference implementations' images, osv-scanner over `uv.lock`, and a link check.

## Options considered

### Where `main` is checked

| Option | Each push to `main` | CI's `allowed-skips` |
|---|---|---|
| **CI on pull requests, Nightly on `main` (chosen)** | Checked once, in full | None |
| CI on pull requests and on `main` (RFC-0003) | Checked twice: CI's affected projects, then Nightly's every project | Every job that runs only on pull requests |

### The title's check

| Option | A title edited after CI passed | What an edit costs |
|---|---|---|
| **Title, a workflow and required check of its own (chosen)** | Checked again | One short job |
| Title as a job in CI (RFC-0003) | Keeps its old result | Nothing |
| CI reruns on `edited` | Checked again | Every job again, for any edit to the title or the description |

## Consequences

- Easier: every squash commit on `main` has a title that release-please can read.
- Easier: `main` is checked once per push, in full, by `nightly.yml`.
- Harder: a failure on `main` shows in Nightly, after the merge, not in CI. Branches must be up to date with `main`, so what merges is what CI tested; what CI didn't select is what Nightly can still catch.
- Harder: a pull request opened with a workflow's own token starts no workflows, so it could never pass either check. release-please and Renovate act as lattice's App for that reason ([ADR-0004](0004-one-github-app-for-release-please-and-renovate.md)).
