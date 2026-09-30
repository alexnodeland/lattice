# ADR-0050: Dashboards from the checkout

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Supersedes the dashboards' releases in [ADR-0021](0021-contributor-compose-and-dev-containers.md) and [ADR-0038](0038-dashboards-generated-tested-and-released.md). Amends [ADR-0023](0023-libraries-and-the-stackr-template.md), how stackr gets them.

## Context

ADR-0021 and ADR-0038 published reflexr's dashboards with each release, as `reflexr-dashboards-<version>.tar.gz`, which stackr's `scripts/fetch-dashboards` downloaded by version, and ADR-0023 had stackr provision them so. In lattice, stackr is a sibling package ([ADR-0048](0048-reflexr-in-lattice.md)), and reflexr's dashboards sit beside it ([stackr RFC-0003](../../stackr/rfcs/0003-one-repository-lattice.md#releases-and-versioning)).

## Decision

- **stackr provisions reflexr's dashboards from the checkout.** Its `compose.yaml` mounts `packages/reflexr/deploy/grafana/dashboards` into Grafana, as a folder of its own beside stackr's and artifactr's.
- **The dashboards' releases retire:** the Release assets workflow and its archive, with stackr's `fetch-dashboards` and its pins. ADR-0038's generated dashboards, their tests and the one-minute min step stand.

## Consequences

- Easier: a renamed metric, the dashboards that query it and the Grafana that shows them change in one pull request, and a stack always shows the dashboards of the code beside it.
- Harder: stackr can't provision one version's dashboards beside another version's code; a stack runs its checkout's.
