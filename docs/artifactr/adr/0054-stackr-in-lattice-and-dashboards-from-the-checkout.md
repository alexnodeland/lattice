# ADR-0054: stackr in lattice, and dashboards from the checkout

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0032](0032-libraries-and-the-stackr-template.md), where stackr lives and how it gets artifactr's dashboards. Supersedes the dashboards' releases in [ADR-0030](0030-compose-and-dev-containers.md) and [ADR-0041](0041-dashboards-generated-tested-and-released.md).

## Context

ADR-0032 put stackr in a repository of its own, which pinned the libraries' versions and dashboards. ADR-0030 and ADR-0041 published artifactr's dashboards with each release, as an archive that stackr's `scripts/fetch-dashboards` downloaded by version. In lattice, stackr is a sibling package, and artifactr's dashboards sit beside it ([stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#releases-and-versioning)).

## Decision

- **stackr is `packages/stackr` in lattice.** ADR-0032's division of work stands: artifactr is a library, and the stack and the application template are stackr's.
- **stackr provisions artifactr's dashboards from the checkout.** Its `compose.yaml` mounts `packages/artifactr/deploy/grafana/dashboards` into Grafana, as a folder of its own beside stackr's and reflexr's.
- **The dashboards' releases retire:** the Release assets workflow, its archive, and the test of its packaging step, with stackr's `fetch-dashboards` and its pins. ADR-0041's generated dashboards, their tests and the one-minute min step stand.
- **artifactr ships no dev container of its own** ([lattice ADR-0009](../../adr/0009-one-dev-container-at-the-root.md)). Its contributor `compose.yaml` and `compose.stackr.yaml` stand.
- **How the template pins the libraries** is RFC-0003's phase 4. Until then it is [stackr ADR-0013](../../stackr/adr/0013-how-the-template-pins-the-libraries.md)'s.

## Consequences

- Easier: a renamed metric, the dashboards that query it and the Grafana that shows them change in one pull request, and a stack always shows the dashboards of the code beside it.
- Harder: stackr can't provision one version's dashboards beside another version's code; a stack runs its checkout's.
