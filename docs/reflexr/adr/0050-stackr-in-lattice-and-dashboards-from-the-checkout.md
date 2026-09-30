# ADR-0050: stackr in lattice, and dashboards from the checkout

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0023](0023-libraries-and-the-stackr-template.md), where stackr lives and how it gets reflexr's dashboards. Supersedes the dashboards' releases in [ADR-0021](0021-contributor-compose-and-dev-containers.md) and [ADR-0038](0038-dashboards-generated-tested-and-released.md).

## Context

ADR-0023 put stackr in a repository of its own, which pinned the libraries' versions and dashboards. ADR-0021 and ADR-0038 published reflexr's dashboards with each release, as `reflexr-dashboards-<version>.tar.gz`, which stackr's `scripts/fetch-dashboards` downloaded by version. In lattice, stackr is a sibling package, and reflexr's dashboards sit beside it ([stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#releases-and-versioning)).

## Decision

- **stackr is `packages/stackr` in lattice.** ADR-0023's division of work stands: reflexr is a library, and the stack and the application template are stackr's.
- **stackr provisions reflexr's dashboards from the checkout.** Its `compose.yaml` mounts `packages/reflexr/deploy/grafana/dashboards` into Grafana, as a folder of its own beside stackr's and artifactr's.
- **The dashboards' releases retire:** the Release assets workflow and its archive, with stackr's `fetch-dashboards` and its pins. ADR-0038's generated dashboards, their tests and the one-minute min step stand.
- **reflexr ships no dev container of its own** ([lattice ADR-0009](../../adr/0009-one-dev-container-at-the-root.md)). Its contributor `compose.yaml` and `compose.stackr.yaml` stand.
- **How the template pins the libraries** is RFC-0003's phase 4. Until then it is [stackr ADR-0013](../../stackr/adr/0013-how-the-template-pins-the-libraries.md)'s.

## Consequences

- Easier: a renamed metric, the dashboards that query it and the Grafana that shows them change in one pull request, and a stack always shows the dashboards of the code beside it.
- Harder: stackr can't provision one version's dashboards beside another version's code; a stack runs its checkout's.
