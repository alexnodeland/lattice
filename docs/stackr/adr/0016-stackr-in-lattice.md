# ADR-0016: stackr in lattice

**Status:** Accepted
**Date:** 2026-09-30
**Deciders:** Alex Nodeland

Amends [ADR-0003](0003-observability-and-gateway-services.md), how Grafana gets the libraries' dashboards; [ADR-0009](0009-local-supabase-as-the-database-adapter.md), what keeps PostgreSQL at Supabase's major version; and [ADR-0011](0011-the-application-template-in-detail.md), where Copier finds the template and when CI generates it.

## Context

stackr was a repository of its own. Copier found its template through the `copier.yml` at that repository's root; its CI generated the template's applications and started the stack on every pull request; Grafana provisioned the libraries' dashboards from their releases, by version; and Dependabot kept its images current. On 2026-09-30 it moved, with its history, into lattice, the family's one repository, as [RFC-0003](../rfcs/0003-one-repository-lattice.md) designed. The template's pins of the libraries are RFC-0003's phase 4, and [ADR-0013](0013-how-the-template-pins-the-libraries.md) stands until then.

## Decision

- **stackr is `packages/stackr`,** a member of lattice's uv workspace that builds nothing, whose tools come from lattice's one `uv.lock`. It keeps its Makefile for the stack, less `install`, `docs` and `docs-serve`, which are lattice's, and `changelog` and `dashboards`, which retired with git-cliff and the dashboards' releases. Its checks are moon tasks: `validate` and `reference` make up its `check`, and `template`, `smoke` and `smoke-app` are CI's Template and Smoke jobs.
- **Copier finds the template from lattice's root** (ADR-0011's "`copier.yml` at the repository's root"). lattice's root `copier.yml` includes `packages/stackr/copier.yml` and sets `_subdirectory: packages/stackr/template`, so an application is generated with `uvx copier copy gh:alexnodeland/lattice my-app`. stackr's scripts render the template from lattice's root, where Copier sees a repository. lattice's tags are prefixed, as in `stackr-v0.1.0`, so Copier finds no release of the template and takes `HEAD`.
- **Template and Smoke run when stackr's own inputs change** (ADR-0011's "on every pull request"): stackr's files, lattice's `copier.yml` or `uv.lock` ([lattice ADR-0002](../../adr/0002-ci-runs-every-affected-project-and-its-dependents.md)). Until phase 4, the template pins the libraries at revisions of their old repositories, so no change in lattice's libraries can reach what it generates.
- **Grafana gets the libraries' dashboards from the checkout** (ADR-0003's "pinned by release"). `compose.yaml` mounts `packages/artifactr/deploy/grafana/dashboards` and reflexr's, each as a folder of its own beside stackr's. `scripts/fetch-dashboards` and its pins in `versions.env` retire.
- **Renovate keeps the images current** (ADR-0009's Dependabot), from lattice's own Actions ([lattice ADR-0005](../../adr/0005-renovate-runs-in-lattices-own-actions.md)). `renovate.json` holds PostgreSQL at major 17, the version local Supabase runs, as Dependabot did, and `scripts/check-config supabase` still fails on a mismatch.
- **release-please releases stackr** as `stackr-v<version>`, with its changelog. stackr ships no wheel ([lattice ADR-0006](../../adr/0006-release-please-first-versions-pre-1-0-bumps-and-what-releases.md)).

## Consequences

- Easier: the template and the libraries it generates applications on are in one repository, which phase 4 needs to test them together.
- Easier: a stack shows the dashboards of the libraries in its own checkout.
- Harder: Copier's documentation recommends one template per repository, since tags are shared. The prefixed tags keep stackr's apart, at the cost of template releases Copier can see (RFC-0003's unresolved questions).
- Harder: until phase 4, an application generated from lattice installs the libraries from their old repositories.
