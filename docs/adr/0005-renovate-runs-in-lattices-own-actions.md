# ADR-0005: Renovate runs in lattice's own Actions

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

## Context

[RFC-0003](../stackr/rfcs/0003-one-repository-lattice.md#ci-and-tooling) replaced the repositories' Dependabot with Renovate, configured in `renovate.json`, and assumed Mend's hosted Renovate app, installed on the repository. On the day, Mend's hosted app turned out to require a Mend account, and to hold write access to the repository from a service outside GitHub. The maintainer chose to keep lattice's infrastructure within GitHub.

## Decision

- **Renovate's open-source CLI runs from `renovate.yml`,** through `renovatebot/github-action`, every day at 05:17 UTC and by hand, one run at a time.
- **It acts as lattice's App** ([ADR-0004](0004-one-github-app-for-release-please-and-renovate.md)), with a token minted for each run and narrowed to what Renovate needs, so its pull requests run CI and Title.
- **It commits through GitHub's API** (`RENOVATE_PLATFORM_COMMIT`), so its commits are signed.
- **`renovate.json` is required, and there is no onboarding.** The configuration is RFC-0003's, with Renovate's `pre-commit` manager, which is off by default, turned on, so the hooks' revisions in `.pre-commit-config.yaml` move too.
- **Dependabot's security updates stay off.** The dependency graph and its alerts are on, since the dependency review action needs the graph; what they report that doesn't apply is recorded as [ADR-0008](0008-one-resolution-litellm-held-at-1-83-0.md) says.

## Options considered

| Option | Services outside GitHub | Runs on | Needs |
|---|---|---|---|
| **The CLI in lattice's Actions (chosen)** | None | lattice's runners, free for a public repository | A workflow, and the App |
| Mend's hosted app (RFC-0003) | Mend, with write access | Mend's | A Mend account |

## Consequences

- Easier: nothing outside GitHub holds access to lattice, and Renovate's runs and logs are Actions runs, beside the rest.
- Harder: Renovate runs once a day, not on Mend's schedule or its webhooks; anything asked of it waits for the next run, or a run by hand.
- Harder: a failed run is lattice's to notice, among its own Actions runs, where Mend's app would have reported on it.
