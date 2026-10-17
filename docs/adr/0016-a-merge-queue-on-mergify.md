# ADR-0016: A merge queue on Mergify

**Status:** Accepted, amended by [ADR-0024](0024-a-parallel-batched-merge-queue.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

[ADR-0003](0003-ci-on-pull-requests-nightly-on-main-and-a-required-title-check.md) requires `CI` and `Title` on branches up to date with `main`, and notes that GitHub offers merge queues only to organizations, so lattice has none. Each merge therefore puts every other open pull request behind `main`. Someone has to bring the next one up to date, wait for its checks, merge it, and repeat. With several pull requests ready at once, that loop is serial, manual and easy to get wrong: two branches updated together race, and the second's checks are wasted.

## Decision

- **Mergify runs the queue**, from `.mergify.yml` at the root. It's free for public repositories, installed as a GitHub App.
- **A pull request joins the queue with the `queue` label**, once its review has passed. Checks alone don't queue anything, because a green pull request isn't necessarily a reviewed one. Removing the label takes it out.
- **The queue is serial, one pull request at a time.** Mergify brings it up to date with `main` and waits for the ruleset's required checks, `CI` and `Title`, which it takes as its merge conditions. Then it squash-merges with the pull request's title, number and description, as GitHub's own squash merge does. Nothing in the ruleset changes: the queue satisfies it rather than bypassing it.

## Options considered

| Option | Who keeps branches current | Cost |
|---|---|---|
| **Mergify, on a label (chosen)** | Mergify, one at a time | A GitHub App, and a hosted service to depend on |
| GitHub's merge queue | GitHub | Needs an organization; `alexnodeland` is a personal account |
| GitHub's auto-merge | Nobody: a pull request behind `main` waits | None, but it leaves the manual loop in place |
| A workflow of our own that updates and merges | A workflow | A queue to write and maintain, and a token that may push to `main` |

## Consequences

- Easier: merging is labelling. Whatever merges was checked against the `main` it lands on, as before.
- Easier: a pull request that changes a workflow can be brought up to date. The GitHub App holds the `workflows` permission that a plain token lacks.
- Harder: merging depends on a hosted service outside GitHub. If Mergify is down, pull requests still merge by hand under the same ruleset.
- Revisit: batching and parallel checks. They need the "up to date" requirement relaxed, with Mergify on the ruleset's bypass list. That's worth it only when the queue is the bottleneck.
