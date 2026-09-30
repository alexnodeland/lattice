# ADR-0054: Dashboards from the checkout

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Supersedes the dashboards' releases in [ADR-0030](0030-compose-and-dev-containers.md) and [ADR-0041](0041-dashboards-generated-tested-and-released.md). Amends [ADR-0032](0032-libraries-and-the-stackr-template.md), how stackr gets them.

## Context

ADR-0030 and ADR-0041 published artifactr's dashboards with each release, as an archive that stackr's `scripts/fetch-dashboards` downloaded by version, and ADR-0032 had stackr provision them so. In lattice, stackr is a sibling package ([ADR-0052](0052-artifactr-in-lattice.md)), and artifactr's dashboards sit beside it ([stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#releases-and-versioning)).

## Decision

- **stackr provisions artifactr's dashboards from the checkout.** Its `compose.yaml` mounts `packages/artifactr/deploy/grafana/dashboards` into Grafana, as a folder of its own beside stackr's and reflexr's.
- **The dashboards' releases retire:** the Release assets workflow, its archive, and the test of its packaging step, with stackr's `fetch-dashboards` and its pins. ADR-0041's generated dashboards, their tests and the one-minute min step stand.

## Consequences

- Easier: a renamed metric, the dashboards that query it and the Grafana that shows them change in one pull request, and a stack always shows the dashboards of the code beside it.
- Harder: stackr can't provision one version's dashboards beside another version's code; a stack runs its checkout's.
